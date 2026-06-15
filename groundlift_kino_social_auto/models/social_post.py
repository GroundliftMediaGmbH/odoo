# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)


class SocialPost(models.Model):
    _inherit = 'social.post'

    gl_kino_issue_id = fields.Many2one('gl.kino.social.issue', string='Kino Social Woche', index=True, ondelete='set null')
    gl_kino_social_type = fields.Selection([
        ('weekly_program', 'Wochenprogramm'),
        ('daily_show', 'Tages-/Film-Post'),
    ], string='Kino Post-Typ', index=True)
    gl_kino_show_key = fields.Char(string='Cinetixx Show-Schlüssel', index=True)
    gl_kino_requires_approval = fields.Boolean(string='Kino Freigabe erforderlich', default=True)
    gl_kino_approved = fields.Boolean(string='Kino freigegeben', default=False)
    gl_kino_planned_date = fields.Datetime(string='Kino geplanter Zeitpunkt')
    gl_kino_auto_generated = fields.Boolean(string='Automatisch aus Kino-Programm erzeugt', default=False, index=True)

    def action_gl_kino_approve_and_schedule(self):
        for post in self:
            post._gl_kino_safe_schedule_without_publish(mark_approved=True)
        return True

    def action_gl_kino_mark_needs_approval(self):
        for post in self:
            post.write({
                'gl_kino_requires_approval': True,
                'gl_kino_approved': False,
            })
            post._gl_kino_force_draft_if_possible()
        return True

    def _gl_kino_force_draft_if_possible(self):
        self.ensure_one()
        if 'state' in self._fields:
            state_field = self._fields['state']
            selection_keys = [item[0] for item in (state_field.selection or [])]
            if 'draft' in selection_keys:
                try:
                    self.sudo().write({'state': 'draft'})
                except Exception:
                    _logger.exception('Could not force kino social.post %s back to draft.', self.id)

    def _gl_kino_safe_schedule_without_publish(self, mark_approved=False):
        """Schedule Kino posts without invoking Odoo's native publish action.

        This mirrors the safety mechanism from the Event Social Automation app:
        future posts are marked as scheduled by fields/state only, so a native
        "Freigeben und planen" button cannot immediately publish a future post.
        """
        self.ensure_one()
        vals = {}
        if mark_approved:
            vals.update({
                'gl_kino_requires_approval': False,
                'gl_kino_approved': True,
            })
        planned_date = self.gl_kino_planned_date
        if not planned_date and 'scheduled_date' in self._fields:
            planned_date = self.scheduled_date
        if planned_date:
            vals['gl_kino_planned_date'] = planned_date
            if 'scheduled_date' in self._fields:
                vals['scheduled_date'] = planned_date
        if 'post_method' in self._fields:
            scheduled_key = self._gl_kino_find_selection_key('post_method', ['scheduled', 'schedule', 'later', 'schedule_later'])
            if scheduled_key:
                vals['post_method'] = scheduled_key
        if 'state' in self._fields:
            scheduled_state = self._gl_kino_find_selection_key('state', ['scheduled', 'schedule'])
            if scheduled_state:
                vals['state'] = scheduled_state
        if vals:
            self.sudo().with_context(gl_kino_skip_approval_hook=True).write(vals)
        return True

    def _gl_kino_planned_datetime(self):
        self.ensure_one()
        planned = self.gl_kino_planned_date
        if not planned and 'scheduled_date' in self._fields:
            planned = self.scheduled_date
        if not planned:
            return False
        try:
            return fields.Datetime.to_datetime(planned)
        except Exception:
            return planned

    def _gl_kino_is_future_scheduled_post(self):
        self.ensure_one()
        if not self.gl_kino_auto_generated:
            return False
        planned = self._gl_kino_planned_datetime()
        if not planned:
            return False
        return planned > (fields.Datetime.now() + timedelta(minutes=2))

    def _gl_kino_intercept_native_publish_action(self, method_name):
        future_posts = self.filtered(lambda post: post._gl_kino_is_future_scheduled_post())
        if future_posts:
            for post in future_posts:
                post._gl_kino_safe_schedule_without_publish(mark_approved=True)
                _logger.info(
                    'Intercepted native social.%s for future Groundlift kino social.post %s; kept scheduled for %s.',
                    method_name,
                    post.id,
                    post._gl_kino_planned_datetime(),
                )
        normal_posts = self - future_posts
        if normal_posts:
            try:
                return getattr(super(SocialPost, normal_posts), method_name)()
            except AttributeError:
                return True
        return True

    def action_post(self):
        return self._gl_kino_intercept_native_publish_action('action_post')

    def action_schedule(self):
        return self._gl_kino_intercept_native_publish_action('action_schedule')

    def action_post_scheduled(self):
        return self._gl_kino_intercept_native_publish_action('action_post_scheduled')

    def _action_post(self):
        return self._gl_kino_intercept_native_publish_action('_action_post')

    def _gl_kino_find_selection_key(self, field_name, preferred_keys):
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
        if not self.env.context.get('gl_kino_skip_approval_hook') and vals.get('gl_kino_approved') is True:
            posts_to_schedule = self.filtered(lambda post: post.gl_kino_auto_generated and post.gl_kino_approved)
            for post in posts_to_schedule:
                post._gl_kino_safe_schedule_without_publish(mark_approved=True)
        return result
