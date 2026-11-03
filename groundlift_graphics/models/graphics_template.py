from odoo import api, fields, models


class GraphicsTemplate(models.Model):
    _name = "gl.graphics.template"
    _description = "Grafikvorlage"
    _order = "sequence, id"

    name = fields.Char(required=True, default="Kino Veranstaltungsankündigung")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Unternehmen",
        default=lambda self: self.env.company,
        index=True,
    )

    default_claim = fields.Text(
        string="Standard-Claim",
        default="KULTUR IM THEATER\nDER ALTEN BRAUEREI STEGEN",
    )
    default_sticker_text = fields.Text(
        string="Standard-Störertext",
        default="LIVE\nON\nSTAGE",
    )
    default_sticker_color = fields.Char(default="#D6331F")
    default_color_1 = fields.Char(default="#000033")
    default_color_2 = fields.Char(default="#002E59")
    output_suffix = fields.Char(
        string="Dateisuffix des Ausspielformats",
        default="Kino",
        help="Wird im automatisch erzeugten Dateinamen verwendet, z. B. Kino, Social_4x5 oder Screen.",
    )

    logo_image = fields.Binary(string="Logo", attachment=True)
    logo_filename = fields.Char(default="Kino_Logo.png")
    frame_image = fields.Binary(string="Rahmen", attachment=True)
    frame_filename = fields.Char(default="Kino_Rahmen.png")
    sticker_image = fields.Binary(string="Original-Störer", attachment=True)
    sticker_filename = fields.Char(default="Kino_Stoerer.png")

    font_regular_name = fields.Char(
        string="Schriftfamilie normal",
        default="Rubik",
        help="CSS-Schriftname. Für exakte Übereinstimmung kann darunter die Originalschrift hochgeladen werden.",
    )
    font_bold_name = fields.Char(
        string="Schriftfamilie fett",
        default="Rubik",
    )
    font_condensed_name = fields.Char(
        string="Schriftfamilie schmal",
        default="Rubik",
    )

    font_light_file = fields.Binary(string="Rubik Light", attachment=True)
    font_light_filename = fields.Char()
    font_regular_file = fields.Binary(string="Rubik Regular", attachment=True)
    font_regular_filename = fields.Char()
    font_medium_file = fields.Binary(string="Rubik Medium", attachment=True)
    font_medium_filename = fields.Char()
    font_bold_file = fields.Binary(string="Rubik Bold", attachment=True)
    font_bold_filename = fields.Char()
    # Legacy field kept for database compatibility with earlier module versions.
    font_condensed_file = fields.Binary(string="Legacy-Schriftdatei schmal", attachment=True)
    font_condensed_filename = fields.Char()

    @api.model
    def get_default_template(self):
        template = self.search(
            [("company_id", "in", [False, self.env.company.id])],
            order="company_id desc, sequence, id",
            limit=1,
        )
        if not template:
            template = self.create({"name": "Kino Veranstaltungsankündigung"})
        return template
