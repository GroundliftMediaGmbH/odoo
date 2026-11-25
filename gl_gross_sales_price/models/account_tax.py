from odoo import api, models


# Odoo exports/imports this computation key in extra_tax_data, also when a
# POS order becomes an invoice. Never activate it on unrelated documents.
GL_GROSS_KEY = "gl_pos_fixed_gross_v1"


def _fixed_gross_unit(base_line):
    """Scope: ordinary single, non-negative, price-excluded percentage VAT.

    Keep native price_unit net in the record and in invoice export. The gross
    unit is recovered from that historical price, not today's product master.
    Native manual tax overrides and special computations take precedence.
    """
    if (base_line.get("computation_key") != GL_GROSS_KEY
            or base_line.get("special_mode") or base_line.get("special_type")
            or base_line.get("filter_tax_function")
            or base_line.get("manual_tax_amounts")
            or base_line.get("manual_total_excluded_currency") is not None
            or base_line.get("manual_total_excluded") is not None):
        return None
    taxes = base_line["tax_ids"]
    if len(taxes) != 1:
        return None
    tax = taxes[0]
    if (tax.amount_type != "percent" or tax.price_include or tax.amount < 0
            or tax.include_base_amount or tax.has_negative_factor):
        return None
    currency = base_line["currency_id"]
    # Do not reinterpret a price that was edited on an invoice or transformed
    # into a special discount/downpayment amount with fractional-cent gross.
    raw = base_line["price_unit"] * (1 + tax.amount / 100.0)
    gross = currency.round(raw)
    if abs(raw - gross) > 0.00001:
        return None
    return gross


class AccountTax(models.Model):
    _inherit = "account.tax"

    @api.model
    def _add_tax_details_in_base_line(self, base_line, company, rounding_method=None):
        gross = _fixed_gross_unit(base_line)
        if gross is None:
            base_line.pop("_gl_fixed_gross_computed", None)
            return super()._add_tax_details_in_base_line(base_line, company, rounding_method=rounding_method)
        # Only the computation sees gross. The stored/exported price is net.
        work = dict(base_line, price_unit=gross, special_mode="total_included")
        result = super()._add_tax_details_in_base_line(work, company, rounding_method=rounding_method)
        base_line["tax_details"] = work["tax_details"]
        base_line["_gl_fixed_gross_computed"] = True
        return result

    @api.model
    def _round_base_lines_tax_details(self, base_lines, company, tax_lines=None):
        result = super()._round_base_lines_tax_details(base_lines, company, tax_lines=tax_lines)
        # Preserve Odoo's tax allocation (global or per line). Allocate any
        # residual cent to NET on the same line, never to customer gross.
        # This also prevents unit-price displays drifting when another item
        # is added. Tax and accounting totals use these same base lines.
        for line in base_lines:
            if not line.get("_gl_fixed_gross_computed") or _fixed_gross_unit(line) is None:
                continue
            details = line["tax_details"]
            if len(details["taxes_data"]) != 1:
                continue
            tax_data = details["taxes_data"][0]
            for suffix, currency in (("_currency", line["currency_id"]), ("", company.currency_id)):
                gross = currency.round(details[f"raw_total_included{suffix}"])
                net = currency.round(gross - tax_data[f"tax_amount{suffix}"])
                details[f"total_excluded{suffix}"] = net
                details[f"total_included{suffix}"] = gross
                details[f"delta_total_excluded{suffix}"] = 0.0
                tax_data[f"base_amount{suffix}"] = net
        return result
