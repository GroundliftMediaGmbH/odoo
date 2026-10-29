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
            "Bei Eingabe eines Bruttopreises wird der steuerfreie Verkaufspreis "
            "mit voller interner Genauigkeit berechnet."
        ),
    )

    gl_gross_price_managed = fields.Boolean(
        string="Bruttopreis-gesteuert",
        default=False,
        copy=True,
        help=(
            "Technisches Kennzeichen: Bei diesem Produkt wurde der Verkaufspreis "
            "aus dem Groundlift-Bruttopreis berechnet. Das POS behält für solche "
            "Produkte die exakte interne Preispräzision bei."
        ),
    )

    @api.depends("list_price", "taxes_id")
    @api.depends_context("company")
    def _compute_gross_list_price(self):
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

    def _gl_exact_net_from_gross(self, gross_price):
        """Return the tax-excluded base without currency rounding.

        Odoo's standard product._get_list_price() uses account.tax.compute_all()
        with its default round_base=True. For EUR this rounds the extracted
        tax-exclusive base to cents, e.g. 3.80 / 1.19 -> 3.19.

        For POS gross-price products we need the raw tax-exclusive amount:
        3.80 / 1.19 -> 3.193277310924...
        """
        self.ensure_one()
        company = self.env.company
        taxes = self.taxes_id._filter_taxes_by_company(company)
        if not taxes:
            return gross_price

        empty_partner = self.env["res.partner"]
        result = taxes.with_context(
            force_price_include=True,
            round_base=False,
        ).compute_all(
            gross_price,
            currency=self.currency_id,
            quantity=1.0,
            product=self,
            partner=empty_partner,
        )
        return result["total_excluded"]

    def _set_list_price_from_gross(self):
        for product in self:
            gross_price = product.gross_list_price or 0.0
            product.list_price = product._gl_exact_net_from_gross(gross_price)
            product.gl_gross_price_managed = True

    def _inverse_gross_list_price(self):
        self._set_list_price_from_gross()

    @api.onchange("gross_list_price")
    def _onchange_gross_list_price(self):
        self._set_list_price_from_gross()

    def action_gl_reapply_gross_price(self):
        """Repair products created with v1.0/v1.1.

        Their visible gross price is correct, but the old module had already
        rounded the net base to currency cents. Re-apply the currently shown
        gross price with the corrected no-rounding calculation.
        """
        for product in self:
            gross_price = product.gross_list_price
            product.list_price = product._gl_exact_net_from_gross(gross_price)
            product.gl_gross_price_managed = True
        return True

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        if "gl_gross_price_managed" not in fields_list:
            fields_list.append("gl_gross_price_managed")
        return fields_list
