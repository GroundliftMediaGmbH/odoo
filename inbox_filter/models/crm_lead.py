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
            records._inbox_filter_auto_sort_if_new()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("inbox_filter_skip_auto") and "stage_id" in vals:
            self._inbox_filter_auto_sort_if_new()
        return res

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
