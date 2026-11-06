from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # IMPORTANT:
    # This is deliberately a normal STORED input field.
    #
    # Older versions used compute= + inverse=. That created a feedback loop:
    # gross input -> exact net -> Odoo tax recomputation -> gross recomputation.
    # Depending on rounding, a value such as 4.20 could therefore jump to a
    # neighbouring cent. From v1.5 onward the entered gross price is the
    # authoritative value and is never recomputed automatically from list_price.
    gross_list_price = fields.Float(
        string="Bruttopreis",
        digits=(16, 2),
        default=0.0,
        copy=True,
        help=(
            "Führender Verkaufspreis inklusive der am Produkt hinterlegten "
            "Verkaufssteuern. Der hier eingegebene Centbetrag wird dauerhaft "
            "gespeichert und nicht erneut aus dem Nettopreis zurückberechnet. "
            "Der exakte Nettopreis wird automatisch in Verkaufspreis geschrieben."
        ),
    )

    gl_gross_price_managed = fields.Boolean(
        string="Bruttopreis-gesteuert",
        default=False,
        copy=True,
        help=(
            "Technisches Kennzeichen: Bei diesem Produkt wird der Standard-"
            "Verkaufspreis aus dem gespeicherten Groundlift-Bruttopreis berechnet. "
            "Das POS behält dafür die exakte interne Netto-Preispräzision bei."
        ),
    )

    def _gl_exact_net_from_gross(self, gross_price):
        """Convert the fixed gross amount to an unrounded tax-exclusive price."""
        self.ensure_one()
        company = self.env.company
        taxes = self.taxes_id._filter_taxes_by_company(company)
        if not taxes:
            return gross_price

        result = taxes.with_context(
            force_price_include=True,
            round_base=False,
        ).compute_all(
            gross_price,
            currency=self.currency_id,
            quantity=1.0,
            product=self,
            partner=self.env["res.partner"],
        )
        return result["total_excluded"]

    def _gl_gross_from_net_for_initialization(self):
        """Reconstruct a 2-decimal gross price from an existing net list_price.

        Used only when installing/upgrading to the stored gross field. It is NOT
        used during normal editing, so it cannot overwrite a user's gross input.
        """
        self.ensure_one()
        company = self.env.company
        taxes = self.taxes_id._filter_taxes_by_company(company)
        if not taxes:
            return self.currency_id.round(self.list_price)

        result = taxes.with_context(
            force_price_include=False,
            round_base=False,
        ).compute_all(
            self.list_price,
            currency=self.currency_id,
            quantity=1.0,
            product=self,
            partner=self.env["res.partner"],
        )
        return self.currency_id.round(result["total_included"])

    def _gl_apply_stored_gross_to_net(self):
        """Apply stored gross price to Odoo's standard net list_price."""
        for product in self:
            net = product._gl_exact_net_from_gross(product.gross_list_price or 0.0)
            product.with_context(gl_skip_gross_sync=True).write({
                "list_price": net,
                "gl_gross_price_managed": True,
            })
        return True

    def _gl_initialize_stored_gross_prices(self):
        """Populate the new stored field without changing existing net prices."""
        for product in self:
            gross = product._gl_gross_from_net_for_initialization()
            product.with_context(gl_skip_gross_sync=True).write({
                "gross_list_price": gross,
            })
        return True

    @api.onchange("gross_list_price")
    def _onchange_gross_list_price(self):
        for product in self:
            product.list_price = product._gl_exact_net_from_gross(
                product.gross_list_price or 0.0
            )
            product.gl_gross_price_managed = True

    @api.onchange("taxes_id")
    def _onchange_taxes_id_gl_gross_price(self):
        """Changing VAT keeps the entered gross amount fixed."""
        for product in self:
            if product.gl_gross_price_managed and product.gross_list_price is not False:
                product.list_price = product._gl_exact_net_from_gross(
                    product.gross_list_price or 0.0
                )

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        for product, vals in zip(products, vals_list):
            if "gross_list_price" in vals:
                product._gl_apply_stored_gross_to_net()
        return products

    def write(self, vals):
        if self.env.context.get("gl_skip_gross_sync"):
            return super().write(vals)

        gross_changed = "gross_list_price" in vals
        taxes_changed = "taxes_id" in vals

        result = super().write(vals)

        # Gross is authoritative. Recalculate net only after the new gross/taxes
        # are already stored, so the helper always sees the final tax setup.
        if gross_changed:
            self._gl_apply_stored_gross_to_net()
        elif taxes_changed:
            self.filtered("gl_gross_price_managed")._gl_apply_stored_gross_to_net()

        return result

    def action_gl_reapply_gross_price(self):
        """Recalculate the exact net price from the stored gross amount."""
        self._gl_apply_stored_gross_to_net()
        return True

    def action_gl_take_gross_from_current_net(self):
        """Explicit escape hatch if a user intentionally edited the net price."""
        for product in self:
            gross = product._gl_gross_from_net_for_initialization()
            product.with_context(gl_skip_gross_sync=True).write({
                "gross_list_price": gross,
            })
        return True

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        if "gl_gross_price_managed" not in fields_list:
            fields_list.append("gl_gross_price_managed")
        return fields_list
