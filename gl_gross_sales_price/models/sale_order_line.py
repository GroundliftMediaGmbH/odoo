from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _gl_event_gross_unit_price(self):
        """Return the rounded customer-facing gross unit price for an event line."""
        self.ensure_one()

        currency = self.currency_id or self.company_id.currency_id
        company = self.company_id or self.env.company
        taxes = self.tax_ids._filter_taxes_by_company(company)

        if not taxes:
            return currency.round(self.price_unit)

        result = taxes.with_context(round_base=False).compute_all(
            self.price_unit,
            currency=currency,
            quantity=1.0,
            product=self.product_id,
            partner=self.order_partner_id,
            rounding_method="round_globally",
        )
        return currency.round(result["total_included"])

    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        """Keep event ticket gross prices authoritative in SO/website checkout.

        The company can stay on `round_per_line` for POS. For event-ticket
        sale lines only, convert the tax computation to a known-total-included
        calculation. This lets Odoo reverse-calculate VAT from e.g. 12.00 gross
        instead of first rounding 11.214953 net to 11.21 and ending at 11.99.
        """
        self.ensure_one()

        if (
            self.event_ticket_id
            and self.product_id
            and "special_mode" not in kwargs
            and "price_unit" not in kwargs
        ):
            kwargs = dict(kwargs)
            kwargs["price_unit"] = self._gl_event_gross_unit_price()
            kwargs["special_mode"] = "total_included"

        return super()._prepare_base_line_for_taxes_computation(**kwargs)
