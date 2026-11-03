from odoo import api, fields, models


class EventEvent(models.Model):
    _inherit = "event.event"

    meta_tracking_mode = fields.Selection([
        ("disabled", "Deaktiviert"),
        ("default", "Groundlift Standard"),
        ("custom", "Eigener Veranstalter-Pixel"),
    ], string="Meta Tracking", default="default", required=True)
    meta_pixel_config_id = fields.Many2one(
        "meta.pixel.config", string="Pixel-Konfiguration",
        domain="[('active', '=', True)]",
    )
    meta_test_mode = fields.Boolean(string="Testmodus")
    meta_track_view_content = fields.Boolean(string="ViewContent", default=True)
    meta_track_add_to_cart = fields.Boolean(string="AddToCart", default=True)
    meta_track_checkout = fields.Boolean(string="InitiateCheckout", default=True)
    meta_track_payment_info = fields.Boolean(string="AddPaymentInfo", default=True)
    meta_track_purchase = fields.Boolean(string="Purchase erfassen", default=True)
    meta_purchase_browser = fields.Boolean(
        string="Purchase über Browser-Pixel",
        default=True,
        help="Sendet den Purchase auf der Odoo-Bestätigungsseite über den Meta Browser Pixel.",
    )
    meta_purchase_capi = fields.Boolean(
        string="Purchase über Conversions API",
        default=True,
        help="Sendet den Purchase zusätzlich serverseitig über die Meta Conversions API. "
             "Bei paralleler Browser- und CAPI-Übermittlung verwendet die App dieselbe Event-ID zur Deduplication.",
    )
    meta_log_count = fields.Integer(compute="_compute_meta_log_count")
    meta_purchase_count = fields.Integer(compute="_compute_meta_stats")
    meta_purchase_value = fields.Monetary(compute="_compute_meta_stats", currency_field="currency_id")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    def _compute_meta_log_count(self):
        grouped = self.env["meta.pixel.log"]._read_group(
            [("event_id", "in", self.ids)], ["event_id"], ["__count"]
        ) if self.ids else []
        counts = {event.id: count for event, count in grouped}
        for record in self:
            record.meta_log_count = counts.get(record.id, 0)

    def _compute_meta_stats(self):
        """Count business purchases once even when Browser Pixel + CAPI both report them.

        Browser and server use the same event_uid for Purchase.  The raw event log keeps
        both transport records for diagnostics, while these event-level KPIs deduplicate
        by event_uid so revenue is never doubled in the event form.
        """
        for record in self:
            logs = self.env["meta.pixel.log"].search([
                ("event_id", "=", record.id),
                ("event_name", "=", "Purchase"),
                ("status", "=", "sent"),
                ("is_test", "=", False),
            ], order="create_date asc, id asc")
            purchases = {}
            for log in logs:
                purchases.setdefault(log.event_uid, log.value or 0.0)
            record.meta_purchase_count = len(purchases)
            record.meta_purchase_value = sum(purchases.values())

    def _get_meta_config(self):
        self.ensure_one()
        if self.meta_tracking_mode == "disabled":
            return self.env["meta.pixel.config"]
        if self.meta_tracking_mode == "custom":
            return self.meta_pixel_config_id
        config_id = int(self.env["ir.config_parameter"].sudo().get_param("meta_pixel.default_config_id") or 0)
        return self.env["meta.pixel.config"].browse(config_id).exists()

    def action_open_meta_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Meta Pixel Ereignisse",
            "res_model": "meta.pixel.log",
            "view_mode": "list,pivot,graph,form",
            "domain": [("event_id", "=", self.id)],
            "context": {"default_event_id": self.id},
        }
