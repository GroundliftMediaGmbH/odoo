# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class EventEvent(models.Model):
    _inherit = "event.event"

    _GL_TARGET_FIELD = "x_studio_event_kalk_ist_ticketumsatz_max_brutto"

    def _gl_sync_sale_price_total_to_studio_field(self):
        """Copy Odoo's standard gross event sales amount into Groundlift's Studio field.

        Source field:
            event.event.sale_price_total

        This field is provided by event_sale and represents the tax-included sales total
        for confirmed sale order lines linked to the event.
        """
        target_field = self._GL_TARGET_FIELD

        if target_field not in self._fields:
            _logger.warning(
                "Groundlift ticket revenue sync skipped: target field %s does not exist on event.event.",
                target_field,
            )
            return False

        for event in self.sudo():
            # sale_price_total is computed by Odoo/event_sale. Reading it here forces the
            # current computed value before we mirror it into the Studio field.
            event.with_context(gl_event_revenue_sync=True).write({
                target_field: event.sale_price_total or 0.0,
            })
        return True

    @api.model
    def _cron_gl_sync_sale_price_total_to_studio_field(self):
        """Daily safety reconciliation in case an edge-case write path was missed."""
        self.sudo().search([])._gl_sync_sale_price_total_to_studio_field()
