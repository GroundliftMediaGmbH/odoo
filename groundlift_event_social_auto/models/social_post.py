# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

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
        self._gl_safe_schedule_without_publish(mark_approved=True)

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
        """Compatibility wrapper: schedule Groundlift posts without calling Odoo's publish action."""
        self.ensure_one()
        return self._gl_safe_schedule_without_publish(mark_approved=True)

    def _gl_safe_schedule_without_publish(self, mark_approved=False):
        """Put the post into Odoo's scheduled state without calling action_post/_action_post.

        In this database the native Social Marketing button labelled similar to
        "Freigeben und planen" can publish immediately even when scheduled_date is
        in the future. Groundlift-generated posts therefore use direct schedule
        fields and our own approval flag instead of invoking the native publish
        action during approval.
        """
        self.ensure_one()
        vals = {}
        if mark_approved:
            vals.update({
                'gl_requires_approval': False,
                'gl_approved': True,
            })

        planned_date = self.gl_planned_date
        if not planned_date and 'scheduled_date' in self._fields:
            planned_date = self.scheduled_date
        if planned_date:
            vals['gl_planned_date'] = planned_date
            if 'scheduled_date' in self._fields:
                vals['scheduled_date'] = planned_date

        if 'post_method' in self._fields:
            scheduled_key = self._gl_find_selection_key('post_method', ['scheduled', 'schedule', 'later', 'schedule_later'])
            if scheduled_key:
                vals['post_method'] = scheduled_key

        if 'state' in self._fields:
            scheduled_state = self._gl_find_selection_key('state', ['scheduled', 'schedule'])
            if scheduled_state:
                vals['state'] = scheduled_state

        if vals:
            self.sudo().with_context(gl_skip_groundlift_approval_hook=True).write(vals)
        return True

    def _gl_planned_datetime(self):
        self.ensure_one()
        planned = self.gl_planned_date
        if not planned and 'scheduled_date' in self._fields:
            planned = self.scheduled_date
        if not planned:
            return False
        try:
            return fields.Datetime.to_datetime(planned)
        except Exception:
            return planned

    def _gl_is_future_groundlift_scheduled_post(self):
        self.ensure_one()
        if not self.gl_auto_generated:
            return False
        planned = self._gl_planned_datetime()
        if not planned:
            return False
        return planned > (fields.Datetime.now() + timedelta(minutes=2))

    def _gl_intercept_native_publish_action(self, method_name):
        """Prevent native publish buttons from immediately posting future Groundlift posts."""
        future_posts = self.filtered(lambda post: post._gl_is_future_groundlift_scheduled_post())
        if future_posts:
            for post in future_posts:
                post._gl_safe_schedule_without_publish(mark_approved=True)
                _logger.info(
                    'Intercepted native social.%s for future Groundlift social.post %s; kept scheduled for %s.',
                    method_name, post.id, post._gl_planned_datetime()
                )
        normal_posts = self - future_posts
        if normal_posts:
            try:
                return getattr(super(SocialPost, normal_posts), method_name)()
            except AttributeError:
                return True
        return True

    def action_post(self):
        return self._gl_intercept_native_publish_action('action_post')

    def action_schedule(self):
        return self._gl_intercept_native_publish_action('action_schedule')

    def action_post_scheduled(self):
        return self._gl_intercept_native_publish_action('action_post_scheduled')

    def _action_post(self):
        return self._gl_intercept_native_publish_action('_action_post')

    def _gl_find_selection_key(self, field_name, preferred_keys):
        field = self._fields.get(field_name)
        if not field or not getattr(field, 'selection', None):
            return False
        keys = [item[0] for item in field.selection]
        for key in preferred_keys:
            if key in keys:
                return key
        return False


    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('gl_skip_groundlift_approval_hook') and vals.get('gl_approved') is True:
            posts_to_schedule = self.filtered(lambda post: post.gl_auto_generated and post.gl_approved)
            for post in posts_to_schedule:
                post._gl_safe_schedule_without_publish(mark_approved=True)
        return result

    def unlink(self):
        events = self.mapped('gl_event_id')
        result = super().unlink()
        if events:
            events._gl_update_social_generated_flags()
        return result
