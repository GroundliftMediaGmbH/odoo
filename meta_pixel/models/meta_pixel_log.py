from odoo import fields, models


class MetaPixelLog(models.Model):
    _name = "meta.pixel.log"
    _description = "Meta Pixel Event Log"
    _order = "create_date desc, id desc"

    create_date = fields.Datetime(readonly=True)
    event_id = fields.Many2one("event.event", required=True, ondelete="cascade", index=True)
    config_id = fields.Many2one("meta.pixel.config", required=True, ondelete="restrict", index=True)
    sale_order_id = fields.Many2one("sale.order", ondelete="set null", index=True)
    event_name = fields.Selection([
        ("PageView", "PageView"),
        ("ViewContent", "ViewContent"),
        ("AddToCart", "AddToCart"),
        ("InitiateCheckout", "InitiateCheckout"),
        ("AddPaymentInfo", "AddPaymentInfo"),
        ("Purchase", "Purchase"),
    ], required=True, index=True)
    event_uid = fields.Char(string="Event ID", required=True, index=True)
    source = fields.Selection([("browser", "Browser Pixel"), ("capi", "Conversions API")], required=True, index=True)
    status = fields.Selection([("sent", "Gesendet"), ("blocked", "Blockiert"), ("error", "Fehler")], required=True, default="sent", index=True)
    is_test = fields.Boolean(string="Test")
    value = fields.Monetary()
    currency_id = fields.Many2one("res.currency")
    response_code = fields.Char()
    response_message = fields.Text()
    page_url = fields.Char()

    _sql_constraints = [
        ("event_source_uid_uniq", "unique(event_uid, source)", "Dieses Tracking-Ereignis wurde über diese Quelle bereits protokolliert."),
    ]
