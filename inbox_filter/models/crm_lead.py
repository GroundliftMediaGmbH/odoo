# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("inbox_filter_skip_auto"):
            # Der Odoo-Mailgateway erzeugt zuerst den CRM-Datensatz und postet
            # anschließend die eigentliche mail.message samt Attachments. In diesem
            # speziellen Gateway-Kontext warten wir deshalb auf
            # _message_post_after_hook(); sonst würden wir zu früh sortieren.
            incoming_gateway_create = bool(
                self.env.context.get("mail_create_nosubscribe")
                and self.env.context.get("mail_create_nolog")
            )
            if not incoming_gateway_create:
                records._inbox_filter_schedule_auto_sort()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("inbox_filter_skip_auto") and "stage_id" in vals:
            # Auch bei einem manuellen/automatischen Wechsel nach CRM: Neu erst
            # am Transaktionsende sortieren. Das vermeidet denselben Race-Condition-
            # Effekt bei Mail-Routing und Weiterleitungen.
            self._inbox_filter_schedule_auto_sort()
        return res

    def _message_post_after_hook(self, message, msg_values):
        """Startet den Filter bei eingehender Mail *nach* Body + Attachments.

        Odoo 19 ruft diesen Hook erst auf, nachdem ``message_post`` die
        ``mail.message`` und ihre Anhänge erstellt hat. Damit ist der komplette
        E-Mail-Eingang vorhanden, bevor der Lead klassifiziert/verschoben wird.
        """
        result = super()._message_post_after_hook(message, msg_values)
        if self.env.context.get("inbox_filter_skip_auto"):
            return result
        if message and message.message_type == "email":
            self._inbox_filter_schedule_auto_sort()
        return result

    def _inbox_filter_schedule_auto_sort(self):
        """Plant die automatische Sortierung einmal pro Lead/Transaktion ein.

        Der bisherige sofortige Aufruf war für eingehende E-Mails zu früh: zu
        diesem Zeitpunkt existierte oft nur der CRM-Lead, nicht aber die danach
        erzeugte mail.message samt Attachments. Odoo 19 stellt dafür den
        Pre-Commit-Hook bereit, den auch das Mail-Modul selbst nutzt.
        """
        records = self.sudo().with_context(active_test=False).exists()
        if not records:
            return True

        precommit = getattr(self.env.cr, "precommit", None)
        if not precommit:
            # Defensive Fallback-Variante für Sonderumgebungen/Tests.
            return records._inbox_filter_auto_sort_if_new()

        pending = precommit.data.setdefault("inbox_filter.auto_sort_lead_ids", set())
        new_ids = [record_id for record_id in records.ids if record_id not in pending]
        if not new_ids:
            return True
        pending.update(new_ids)
        precommit.add(records.browse(new_ids)._inbox_filter_auto_sort_if_new)
        return True

    def _inbox_filter_auto_sort_if_new(self):
        service = self.env["inbox.filter.service"].sudo()
        for lead in self.sudo().with_context(active_test=False):
            try:
                service.auto_sort_lead(lead)
            except Exception:  # noqa: BLE001
                # Die automatische Sortierung darf das Anlegen/Verschieben eines CRM-Leads nie blockieren.
                _logger.exception("Inbox Filter auto-sort unexpectedly crashed for crm.lead %s", lead.id)
        return True

    def action_inbox_filter_sort(self):
        return self.env["inbox.filter.service"].run_sort_new_leads_action()

    def action_open_inbox_filter(self):
        return self.env.ref("inbox_filter.action_inbox_filter_workspace").read()[0]
