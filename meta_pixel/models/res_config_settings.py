from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    meta_pixel_default_config_id = fields.Many2one(
        "meta.pixel.config",
        string="Standard-Pixel für Groundlift-Veranstaltungen",
        config_parameter="meta_pixel.default_config_id",
    )
