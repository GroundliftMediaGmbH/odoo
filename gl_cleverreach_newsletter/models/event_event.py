# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class EventEvent(models.Model):
    _inherit = "event.event"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._gl_cr_queue_if_announced()
        return records

    def write(self, vals):
        old_stage_by_id = {}
        if "stage_id" in vals:
            old_stage_by_id = {rec.id: rec.stage_id.id for rec in self}
        result = super().write(vals)
        if "stage_id" in vals:
            for rec in self:
                if old_stage_by_id.get(rec.id) != rec.stage_id.id:
                    rec._gl_cr_queue_if_announced()
        return result

    def _gl_cr_queue_if_announced(self):
        Config = self.env["gl.cleverreach.newsletter.config"].sudo()
        configs = Config.search([("active", "=", True)])
        if not configs or "stage_id" not in self._fields:
            return False
        for event in self.sudo():
            stage = event.stage_id
            if not stage or not stage.name:
                continue
            for config in configs:
                if stage.name.strip().casefold() == (config.announced_stage_name or "Angekündigt").strip().casefold():
                    try:
                        config._queue_event(event, stage=stage)
                    except Exception:
                        _logger.exception("Could not queue event %s for CleverReach newsletter config %s", event.id, config.id)
        return True
