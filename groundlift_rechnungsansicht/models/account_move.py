# -*- coding: utf-8 -*-
import re
from collections import OrderedDict

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    groundlift_invoice_description = fields.Text(
        string="Beschreibung der Rechnung",
        help=(
            "Frei formatierbarer Einleitungstext, der im PDF oberhalb der "
            "Rechnungspositionen ausgegeben wird. Zeilenumbrüche bleiben erhalten."
        ),
        copy=True,
    )
    groundlift_invoice_side_note = fields.Text(
        string="Zusatzangaben rechts",
        help=(
            "Optionaler Textblock rechts neben der Dokumentüberschrift, zum Beispiel "
            "für Kostenstelle, PSP-Element oder projektspezifische Angaben."
        ),
        copy=True,
    )

    def _groundlift_invoice_display_number(self):
        """Return the customer-facing invoice number for the Groundlift PDF layout.

        Odoo's internal sequence can contain slashes, for example ``RE/2026/0003``.
        The Groundlift invoice layout must print this as ``RE202600003``:
        prefix + year/period + last sequence block padded to five digits.
        """
        self.ensure_one()
        raw_number = (self.name if self.name and self.name != "/" else False) or self.ref or "Entwurf"
        raw_number = str(raw_number).strip()

        parts = raw_number.split("/")
        if len(parts) >= 3 and parts[-1].isdigit():
            return "".join(parts[:-1]) + parts[-1].zfill(5)

        return re.sub(r"[^0-9A-Za-z]+", "", raw_number) or "Entwurf"

    def _groundlift_invoice_tax_summary_by_rate(self):
        """Return VAT/tax summary lines grouped by percentage rate for the PDF.

        The report needs a human-readable tax breakdown such as:
        Umsatzsteuer 7,00 % (aus 700,00 € netto) 49,00 €
        Umsatzsteuer 19,00 % (aus 610,00 € netto) 115,90 €

        The calculation uses the invoice line taxes from ``account.move.line.tax_ids``.
        These are the taxes that Odoo has actually applied after product settings and
        fiscal-position mapping. For normal German VAT invoices this gives one group
        per used USt.-Satz. Lines without a tax are grouped as 0,00 % so that invoices
        with tax-exempt/zero-rated products still show an explicit VAT line.
        """
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        groups = OrderedDict()

        def _key(rate, tax_id=0, tax_name=""):
            # Group by the visible percentage rate. ``tax_id`` remains in the key only
            # for non-percentage taxes where the rate cannot be derived safely.
            if rate is None:
                return ("tax", tax_id, tax_name or "")
            return ("rate", round(float(rate), 6))

        def _add_group(rate, base, amount, tax_id=0, tax_name=""):
            key = _key(rate, tax_id=tax_id, tax_name=tax_name)
            if key not in groups:
                groups[key] = {
                    "rate": rate,
                    "rate_label": self._groundlift_format_tax_rate(rate),
                    "label": self._groundlift_tax_summary_label(rate, tax_name),
                    "base": 0.0,
                    "amount": 0.0,
                }
            groups[key]["base"] += base or 0.0
            groups[key]["amount"] += amount or 0.0

        for line in self.invoice_line_ids:
            if line.display_type != "product":
                continue

            tax_details = line._groundlift_invoice_tax_details_for_summary()
            if not tax_details:
                _add_group(0.0, line.price_subtotal, 0.0)
                continue

            for detail in tax_details:
                _add_group(
                    detail.get("rate"),
                    detail.get("base"),
                    detail.get("amount"),
                    tax_id=detail.get("tax_id") or 0,
                    tax_name=detail.get("tax_name") or "",
                )

        result = list(groups.values())
        result.sort(
            key=lambda item: (
                item["rate"] is None,
                item["rate"] if item["rate"] is not None else 999999.0,
                item["label"],
            )
        )

        for item in result:
            if currency:
                item["base"] = currency.round(item["base"])
                item["amount"] = currency.round(item["amount"])
        return result

    def _groundlift_tax_summary_label(self, rate, tax_name=""):
        if rate is None:
            return tax_name or "Umsatzsteuer"
        return "Umsatzsteuer %s" % self._groundlift_format_tax_rate(rate, with_percent=True)

    def _groundlift_format_tax_rate(self, rate, with_percent=False):
        if rate is None:
            return ""
        value = ("%.2f" % float(rate)).replace(".", ",")
        return "%s %%" % value if with_percent else value


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _groundlift_invoice_tax_rate_display(self):
        """Return the USt.-Satz displayed in the invoice line table.

        The value is intentionally based on the invoice line's ``tax_ids``. In Odoo,
        those taxes are generated from the product configuration and fiscal-position
        mapping, so the PDF mirrors the tax setup that is actually used on the invoice.
        """
        self.ensure_one()
        rates = []
        non_percent_names = []

        taxes = self.tax_ids
        if not taxes:
            return "0,00"

        for tax in taxes:
            if tax.amount_type == "group":
                children = tax.children_tax_ids
                for child in children:
                    if child.amount_type in ("percent", "division"):
                        rates.append(child.amount)
                    else:
                        non_percent_names.append(child.name)
            elif tax.amount_type in ("percent", "division"):
                rates.append(tax.amount)
            else:
                non_percent_names.append(tax.name)

        if rates:
            unique_rates = []
            for rate in rates:
                rounded = round(float(rate), 6)
                if rounded not in [round(float(existing), 6) for existing in unique_rates]:
                    unique_rates.append(rate)
            return " / ".join(("%.2f" % float(rate)).replace(".", ",") for rate in sorted(unique_rates))

        return " / ".join(non_percent_names) if non_percent_names else "0,00"

    def _groundlift_invoice_tax_details_for_summary(self):
        """Return computed tax details for one invoice line.

        Uses ``account.tax.compute_all`` where possible so discounts, included taxes,
        quantities and fiscal-position-mapped line taxes are respected. If a future
        Odoo signature changes, the method falls back to a conservative percentage
        calculation from ``price_subtotal``.
        """
        self.ensure_one()
        taxes = self.tax_ids
        if not taxes:
            return []

        move = self.move_id
        currency = move.currency_id or move.company_id.currency_id
        price_unit = self.price_unit * (1.0 - ((self.discount or 0.0) / 100.0))
        is_refund = move.move_type in ("out_refund", "in_refund")

        try:
            computed = taxes.compute_all(
                price_unit,
                currency=currency,
                quantity=self.quantity,
                product=self.product_id,
                partner=move.partner_id,
                is_refund=is_refund,
                handle_price_include=True,
            )
            tax_details = []
            for tax_data in computed.get("taxes", []):
                tax = self.env["account.tax"].browse(tax_data.get("id"))
                rate = None
                if tax and tax.amount_type in ("percent", "division"):
                    rate = tax.amount
                tax_details.append({
                    "tax_id": tax.id if tax else 0,
                    "tax_name": tax.name if tax else tax_data.get("name", ""),
                    "rate": rate,
                    "base": tax_data.get("base", computed.get("total_excluded", self.price_subtotal)),
                    "amount": tax_data.get("amount", 0.0),
                })
            return tax_details
        except TypeError:
            # Some Odoo versions rename optional compute_all keyword arguments.
            try:
                computed = taxes.compute_all(
                    price_unit,
                    currency,
                    self.quantity,
                    self.product_id,
                    move.partner_id,
                    is_refund=is_refund,
                )
                tax_details = []
                for tax_data in computed.get("taxes", []):
                    tax = self.env["account.tax"].browse(tax_data.get("id"))
                    rate = tax.amount if tax and tax.amount_type in ("percent", "division") else None
                    tax_details.append({
                        "tax_id": tax.id if tax else 0,
                        "tax_name": tax.name if tax else tax_data.get("name", ""),
                        "rate": rate,
                        "base": tax_data.get("base", computed.get("total_excluded", self.price_subtotal)),
                        "amount": tax_data.get("amount", 0.0),
                    })
                return tax_details
            except Exception:
                return self._groundlift_invoice_tax_details_fallback()
        except Exception:
            return self._groundlift_invoice_tax_details_fallback()

    def _groundlift_invoice_tax_details_fallback(self):
        self.ensure_one()
        details = []
        for tax in self.tax_ids:
            if tax.amount_type == "group":
                for child in tax.children_tax_ids:
                    details.extend(self._groundlift_tax_detail_from_tax(child))
            else:
                details.extend(self._groundlift_tax_detail_from_tax(tax))
        return details

    def _groundlift_tax_detail_from_tax(self, tax):
        self.ensure_one()
        rate = tax.amount if tax.amount_type in ("percent", "division") else None
        amount = 0.0
        if rate is not None:
            amount = self.price_subtotal * float(rate) / 100.0
        return [{
            "tax_id": tax.id,
            "tax_name": tax.name,
            "rate": rate,
            "base": self.price_subtotal,
            "amount": amount,
        }]
