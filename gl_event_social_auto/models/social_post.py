# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SocialPost(models.Model):
    _inherit = 'social.post'

    gl_event_id = fields.Many2one('event.event', string='Groundlift Veranstaltung', index=True, ondelete='set null')
    gl_event_social_type = fields.Selection([
        ('announcement', 'Erstankündigung'),
        ('reminder_3d', 'Reminder 3 Tage vorher'),
        ('event_day', 'Eventtag'),
        ('soldout', 'Ausverkauft'),
        ('event_day_soldout', 'Eventtag ausverkauft'),
        ('completed', 'Nachbericht'),
        ('gap_filler', 'Lückenfüller'),
        ('weekly_promo', 'Wöchentlicher Werbepost'),
    ], string='Groundlift Post-Typ', index=True)
    gl_requires_approval = fields.Boolean(string='Groundlift Freigabe erforderlich', default=True)
    gl_approved = fields.Boolean(string='Groundlift freigegeben', default=False)
    gl_planned_date = fields.Datetime(string='Groundlift geplanter Zeitpunkt')
    gl_latest_planned_date = fields.Datetime(string='Groundlift spätester zulässiger Zeitpunkt')
    gl_auto_generated = fields.Boolean(string='Automatisch aus Veranstaltung erzeugt', default=False, index=True)

    def action_gl_approve_and_schedule(self):
        for post in self:
            post._gl_approve_and_schedule_one()
        return True

    def action_gl_mark_needs_approval(self):
        for post in self:
            post.write({
                'gl_requires_approval': True,
                'gl_approved': False,
            })
            post._gl_force_draft_if_possible()
        return True

    def _gl_approve_and_schedule_one(self):
        self.ensure_one()
        vals = {
            'gl_requires_approval': False,
            'gl_approved': True,
        }
        if self.gl_planned_date and 'scheduled_date' in self._fields:
            vals['scheduled_date'] = self.gl_planned_date
        self.write(vals)
        self._gl_schedule_if_possible()

    def _gl_force_draft_if_possible(self):
        self.ensure_one()
        if 'state' in self._fields:
            state_field = self._fields['state']
            selection_keys = [item[0] for item in (state_field.selection or [])]
            if 'draft' in selection_keys:
                try:
                    self.sudo().write({'state': 'draft'})
                except Exception:
                    _logger.exception('Could not force social.post %s back to draft.', self.id)

    def _gl_schedule_if_possible(self):
        """Mark the post as approved and scheduled without publishing immediately.

        Important: do NOT call Odoo Social actions such as action_post(),
        action_schedule() or _action_post() here. In some Odoo Social Marketing
        versions those methods publish immediately, even when a future
        scheduled_date is present.

        This method only writes the schedule-related fields. Odoo's own social
        cron can then publish the record when scheduled_date is reached.
        """
        self.ensure_one()
        vals = {}

        if 'post_method' in self._fields:
            scheduled_key = self._gl_find_selection_key(
                'post_method',
                ['scheduled', 'schedule', 'later', 'schedule_later']
            )
            if scheduled_key:
                vals['post_method'] = scheduled_key

        if self.gl_planned_date and 'scheduled_date' in self._fields:
            vals['scheduled_date'] = self.gl_planned_date

        if 'state' in self._fields:
            scheduled_state = self._gl_find_selection_key('state', ['scheduled', 'schedule'])
            if scheduled_state:
                vals['state'] = scheduled_state

        if vals:
            try:
                self.sudo().write(vals)
                return True
            except Exception:
                _logger.exception('Could not mark social.post %s as scheduled.', self.id)
                return False

        _logger.warning(
            'Could not schedule social.post %s safely: no compatible schedule fields found.',
            self.id,
        )
        return False

    def _gl_find_selection_key(self, field_name, preferred_keys):
        field = self._fields.get(field_name)
        if not field or not getattr(field, 'selection', None):
            return False
        keys = [item[0] for item in field.selection]
        for key in preferred_keys:
            if key in keys:
                return key
        return False

    def unlink(self):
        events = self.mapped('gl_event_id')
        result = super().unlink()
        if events:
            events._gl_update_social_generated_flags()
        return result
