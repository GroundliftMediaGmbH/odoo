from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    gross_list_price = fields.Float(
        string="Bruttopreis",
        compute="_compute_gross_list_price",
        inverse="_inverse_gross_list_price",
        digits=(16, 2),
        help=(
            "Verkaufspreis inklusive der am Produkt hinterlegten Verkaufssteuern. "
            "Bei der Eingabe eines Bruttopreises berechnet Odoo automatisch den "
            "präzisen Nettopreis und speichert ihn im Feld Verkaufspreis."
        ),
    )

    @api.depends("list_price", "taxes_id")
    @api.depends_context("company")
    def _compute_gross_list_price(self):
        """Show the customer-facing gross price for the current company."""
        company = self.env.company
        empty_partner = self.env["res.partner"]

        for product in self:
            taxes = product.taxes_id._filter_taxes_by_company(company)
            if not taxes:
                product.gross_list_price = product.list_price
                continue

            result = taxes.compute_all(
                product.list_price,
                currency=product.currency_id,
                quantity=1.0,
                product=product,
                partner=empty_partner,
            )
            product.gross_list_price = result["total_included"]

    def _set_list_price_from_gross(self):
        """
        Convert the entered public/gross price back to the exact product
        sales price. Odoo 19 already provides _get_list_price() for exactly
        this tax-aware conversion, including price-included taxes.
        """
        for product in self:
            product.list_price = product._get_list_price(
                product.gross_list_price or 0.0
            )

    def _inverse_gross_list_price(self):
        self._set_list_price_from_gross()

    @api.onchange("gross_list_price")
    def _onchange_gross_list_price(self):
        # Makes the precise net price visible immediately in the form,
        # without waiting for the record to be saved.
        self._set_list_price_from_gross()
