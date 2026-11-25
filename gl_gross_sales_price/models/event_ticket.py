from odoo import api, models


class EventEventTicket(models.Model):
    _inherit = "event.event.ticket"

    def _gl_tax_included_amount_precise(self, amount):
        """Compute public gross price without pre-rounding the net base.

        Odoo 19's event_product implementation calls account.tax.compute_all()
        with the company's rounding method. If the company uses
        `round_per_line`, a ticket such as:

            11.214953 net + 7% VAT

        can become:
            11.21 base + 0.78 VAT = 11.99

        although the mathematically intended gross amount is 12.00.

        For the public event gross amount, use global/raw tax precision and
        round only the final tax-included amount to the currency precision.
        """
        self.ensure_one()

        currency = self.currency_id or self.event_id.company_id.currency_id
        company = self.event_id.company_id or self.env.company
        taxes = self.product_id.taxes_id._filter_taxes_by_company(company)

        if not taxes:
            return currency.round(amount)

        result = taxes.with_context(round_base=False).compute_all(
            amount,
            currency=currency,
            quantity=1.0,
            product=self.product_id,
            rounding_method="round_globally",
        )
        return currency.round(result["total_included"])

    @api.depends("product_id", "product_id.taxes_id", "price")
    def _compute_price_incl(self):
        for ticket in self:
            if ticket.product_id and ticket.price:
                ticket.price_incl = ticket._gl_tax_included_amount_precise(
                    ticket.price
                )
            else:
                ticket.price_incl = 0.0

    @api.depends("product_id", "product_id.taxes_id", "price_reduce")
    def _compute_price_reduce_taxinc(self):
        for ticket in self:
            if ticket.product_id:
                ticket.price_reduce_taxinc = (
                    ticket._gl_tax_included_amount_precise(ticket.price_reduce)
                )
            else:
                ticket.price_reduce_taxinc = 0.0
