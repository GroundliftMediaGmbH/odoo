from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    groundlift_event_checkout_enabled = fields.Boolean(
        string="Groundlift One-Page Checkout aktiv",
        default=True,
        help=(
            "Wenn aktiv, verwendet die Website den Groundlift Ticketselektor und "
            "den Groundlift One-Page-Checkout. Wenn deaktiviert, greift wieder "
            "der Odoo-Standardablauf für Veranstaltungen und Checkout."
        ),
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    groundlift_event_checkout_enabled = fields.Boolean(
        string="Groundlift One-Page Checkout aktiv",
        related="website_id.groundlift_event_checkout_enabled",
        readonly=False,
    )

    def action_groundlift_checkout_use_standard(self):
        self.ensure_one()
        website = self.website_id
        if website:
            website.sudo().write({"groundlift_event_checkout_enabled": False})
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_groundlift_checkout_use_custom(self):
        self.ensure_one()
        website = self.website_id
        if website:
            website.sudo().write({"groundlift_event_checkout_enabled": True})
        return {"type": "ir.actions.client", "tag": "reload"}
