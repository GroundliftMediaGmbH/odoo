from odoo import api, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    @api.model
    def _gl_base_line_uses_gross_pos_rounding(self, base_line):
        """Return True only for Groundlift gross-price-managed POS lines.

        The marker is deliberately narrow. Normal sales, purchases and invoices
        continue to use the company's configured tax rounding method.
        """
        if base_line.get("_gl_gross_price_managed"):
            return True

        record = base_line.get("record")
        if record:
            # POS order line itself.
            if getattr(record, "_name", None) == "pos.order.line":
                product = record.product_id
                if product and product.product_tmpl_id.gl_gross_price_managed:
                    return True

            # Invoice/account move line generated from a managed POS line.
            extra_tax_data = getattr(record, "extra_tax_data", None)
            if isinstance(extra_tax_data, dict) and extra_tax_data.get(
                "gl_gross_price_managed"
            ):
                return True

        return False

    @api.model
    def _add_tax_details_in_base_lines(self, base_lines, company):
        """Use per-line rounding only for managed POS gross-price lines.

        Odoo 19 normally takes company.tax_calculation_rounding_method here.
        With exact net prices derived from fixed gross prices, global tax
        redistribution can remove/add one cent from the customer-facing basket.
        We therefore force 'round_per_line' for these POS lines only.
        """
        if not any(self._gl_base_line_uses_gross_pos_rounding(bl) for bl in base_lines):
            return super()._add_tax_details_in_base_lines(base_lines, company)

        for base_line in base_lines:
            rounding_method = (
                "round_per_line"
                if self._gl_base_line_uses_gross_pos_rounding(base_line)
                else None
            )
            self._add_tax_details_in_base_line(
                base_line,
                company,
                rounding_method=rounding_method,
            )
