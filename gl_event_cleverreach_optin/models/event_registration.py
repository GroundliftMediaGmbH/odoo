import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class EventRegistration(models.Model):
    _inherit = "event.registration"

    gl_cr_newsletter_optin = fields.Boolean(
        string="Friendly Newsletter",
        default=False,
        copy=False,
        help="Vom Gast im Ticket-/Anmeldeprozess aktiv erteilte Newsletter-Auswahl.",
    )
    gl_cr_newsletter_optin_at = fields.Datetime(
        string="Newsletter-Auswahl am",
        readonly=True,
        copy=False,
    )
    gl_cr_newsletter_optin_source = fields.Char(
        string="Newsletter-Auswahl Quelle",
        readonly=True,
        copy=False,
    )
    gl_cr_newsletter_sync_state = fields.Selection(
        [
            ("not_requested", "Nicht angefragt"),
            ("pending", "Wartet"),
            ("synced", "Übertragen"),
            ("exists", "Bereits vorhanden"),
            ("error", "Fehler"),
        ],
        string="CleverReach-Status",
        default="not_requested",
        readonly=True,
        copy=False,
    )
    gl_cr_newsletter_synced_at = fields.Datetime(
        string="CleverReach geprüft/übertragen am",
        readonly=True,
        copy=False,
    )
    gl_cr_newsletter_sync_message = fields.Text(
        string="CleverReach-Meldung",
        readonly=True,
        copy=False,
    )
    gl_cr_newsletter_bulk_imported = fields.Boolean(
        string="Über Bestandsimport verarbeitet",
        readonly=True,
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if vals.get("gl_cr_newsletter_optin"):
                vals.setdefault("gl_cr_newsletter_optin_at", now)
                vals.setdefault("gl_cr_newsletter_sync_state", "pending")
                vals.setdefault(
                    "gl_cr_newsletter_optin_source",
                    "website_event_ticket_modal",
                )
            prepared.append(vals)

        records = super().create(prepared)
        if not self.env.context.get("gl_cr_skip_event_sync"):
            records._gl_cr_try_sync_newsletter()
        return records

    def write(self, vals):
        if self.env.context.get("gl_cr_skip_event_sync"):
            return super().write(vals)

        vals = dict(vals)
        if "gl_cr_newsletter_optin" in vals:
            if vals.get("gl_cr_newsletter_optin"):
                vals.setdefault("gl_cr_newsletter_optin_at", fields.Datetime.now())
                vals.setdefault("gl_cr_newsletter_sync_state", "pending")
            else:
                # Do not remove/unsubscribe a CleverReach receiver here: the same
                # address may have a valid newsletter relationship from elsewhere.
                vals["gl_cr_newsletter_sync_state"] = "not_requested"
                vals["gl_cr_newsletter_sync_message"] = False

        result = super().write(vals)
        relevant = {
            "gl_cr_newsletter_optin",
            "email",
            "name",
            "state",
            "sale_order_line_id",
        }
        if relevant.intersection(vals):
            self._gl_cr_try_sync_newsletter()
        return result

    def _gl_cr_is_sync_eligible(self):
        self.ensure_one()
        if not self.gl_cr_newsletter_optin or not self.email:
            return False
        if self.state not in ("open", "done"):
            return False

        # A priced web ticket is not considered bought until its sale order is
        # confirmed. Registrations are created before checkout and linked to the
        # order line afterwards, so this guard prevents premature subscribing.
        ticket = self.event_ticket_id
        if ticket and (ticket.price or 0.0) > 0:
            line = self.sale_order_line_id
            if not line or line.order_id.state not in ("sale", "done"):
                return False
        return True

    def _gl_cr_write_status(self, values):
        self.with_context(gl_cr_skip_event_sync=True).sudo().write(values)

    def _gl_cr_try_sync_newsletter(self):
        if self.env.context.get("gl_cr_skip_event_sync"):
            return

        eligible = self.filtered(lambda rec: rec._gl_cr_is_sync_eligible())
        if not eligible:
            return

        Config = self.env["gl.cleverreach.newsletter.config"].sudo()
        config, group = Config._gl_event_find_live_config_and_group()
        if not config or not group:
            eligible._gl_cr_write_status(
                {
                    "gl_cr_newsletter_sync_state": "error",
                    "gl_cr_newsletter_sync_message": _(
                        "Keine aktive CleverReach-Konfiguration mit der Liste "
                        "'Newsletter_allgemein' gefunden. Bitte in CleverReach "
                        "Newsletter > Einstellungen die Listen importieren und "
                        "den Zielnamen prüfen."
                    ),
                }
            )
            return

        for registration in eligible:
            # A successfully processed record normally needs no repeated API call.
            # E-mail/name changes deliberately retrigger via write(), but only
            # pending/error records are automatically retried here.
            if registration.gl_cr_newsletter_sync_state in ("synced", "exists"):
                continue
            try:
                state, message = config._gl_event_sync_registration(
                    registration, group=group
                )
                if state == "invalid_email":
                    registration._gl_cr_write_status(
                        {
                            "gl_cr_newsletter_sync_state": "error",
                            "gl_cr_newsletter_sync_message": message,
                        }
                    )
                    continue
                registration._gl_cr_write_status(
                    {
                        "gl_cr_newsletter_sync_state": state,
                        "gl_cr_newsletter_synced_at": fields.Datetime.now(),
                        "gl_cr_newsletter_sync_message": message,
                    }
                )
            except Exception as exc:
                # CleverReach must never make registration/payment fail.
                _logger.exception(
                    "CleverReach event recipient sync failed for registration %s",
                    registration.id,
                )
                registration._gl_cr_write_status(
                    {
                        "gl_cr_newsletter_sync_state": "error",
                        "gl_cr_newsletter_sync_message": str(exc)[:1000],
                    }
                )
