from odoo import models


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    def _prepare_base_line_for_taxes_computation(self):
        values = super()._prepare_base_line_for_taxes_computation()
        self.ensure_one()
        if self.product_id.product_tmpl_id.gl_gross_price_managed:
            values["_gl_gross_price_managed"] = True
        return values


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _get_invoice_lines_values(self, line_values, pos_line, move_type):
        vals = super()._get_invoice_lines_values(line_values, pos_line, move_type)

        # Section/combo lines do not contain tax data and need no marker.
        if (
            isinstance(vals, dict)
            and pos_line
            and pos_line.product_id
            and pos_line.product_id.product_tmpl_id.gl_gross_price_managed
            and vals.get("display_type") != "line_section"
        ):
            extra_tax_data = dict(vals.get("extra_tax_data") or {})
            extra_tax_data["gl_gross_price_managed"] = True
            vals["extra_tax_data"] = extra_tax_data

        return vals
