from odoo import fields, models


class EventEvent(models.Model):
    _inherit = "event.event"

    graphics_poster_ids = fields.One2many(
        "gl.graphics.poster",
        "event_id",
        string="Grafiken",
    )
    graphics_poster_count = fields.Integer(
        string="Grafiken",
        compute="_compute_graphics_poster_count",
    )

    def _compute_graphics_poster_count(self):
        grouped = self.env["gl.graphics.poster"]._read_group(
            [("event_id", "in", self.ids)],
            ["event_id"],
            ["__count"],
        )
        counts = {event.id: count for event, count in grouped}
        for event in self:
            event.graphics_poster_count = counts.get(event.id, 0)

    def action_create_graphics_poster(self):
        self.ensure_one()
        poster = self.env["gl.graphics.poster"].create({"event_id": self.id})
        return poster.action_open_editor()

    def action_view_graphics_posters(self):
        self.ensure_one()
        action = self.env.ref("groundlift_graphics.action_graphics_poster").read()[0]
        action["domain"] = [("event_id", "=", self.id)]
        action["context"] = {"default_event_id": self.id}
        return action
