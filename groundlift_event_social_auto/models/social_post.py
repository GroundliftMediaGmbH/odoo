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

    gl_retry_source_post_id = fields.Many2one(
        'social.post',
        string='Wiederholung von Social Post',
        index=True,
        ondelete='set null',
        copy=False,
    )
    gl_retry_platform = fields.Selection([
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
    ], string='Wiederholungs-Plattform', copy=False, index=True)
    gl_retry_attempted_at = fields.Datetime(string='Direkt erneut gepostet am', copy=False)
    gl_has_facebook_target = fields.Boolean(
        string='Facebook-Ziel vorhanden',
        compute='_compute_gl_platform_targets',
    )
    gl_has_instagram_target = fields.Boolean(
        string='Instagram-Ziel vorhanden',
        compute='_compute_gl_platform_targets',
    )

    @api.depends('account_ids', 'account_ids.media_id')
    def _compute_gl_platform_targets(self):
        for post in self:
            accounts = post._gl_target_accounts()
            post.gl_has_facebook_target = bool(post._gl_filter_accounts_by_platform(accounts, 'facebook'))
            post.gl_has_instagram_target = bool(post._gl_filter_accounts_by_platform(accounts, 'instagram'))

    def _gl_account_field_name(self):
        """Return the social account field used by this Odoo Social version."""
        if 'account_ids' in self._fields:
            return 'account_ids'
        if 'social_account_ids' in self._fields:
            return 'social_account_ids'
        return False

    def _gl_target_accounts(self):
        """Return the accounts selected on the post.

        The fallback through social.live.post keeps the retry buttons usable on
        older/published records where Odoo no longer exposes account_ids in the
        same way as on drafts.
        """
        self.ensure_one()
        account_field_name = self._gl_account_field_name()
        accounts = self.env['social.account']
        if account_field_name:
            accounts |= self[account_field_name]
        if accounts:
            return accounts

        # Only inspect live-post relations as a fallback. Avoiding this access
        # on normal records also prevents unnecessary evaluation of Odoo's live
        # post status computations.
        for field in self._fields.values():
            if getattr(field, 'comodel_name', False) != 'social.live.post':
                continue
            try:
                live_posts = self[field.name]
            except Exception:
                continue
            for account_field in ('account_id', 'social_account_id'):
                if account_field in live_posts._fields:
                    accounts |= live_posts.mapped(account_field)
                    break
        return accounts

    @api.model
    def _gl_platform_search_text(self, account):
        media = account.media_id if 'media_id' in account._fields else False
        values = []
        for record in (account, media):
            if not record:
                continue
            for field_name in ('name', 'display_name', 'media_type', 'technical_name', 'tech_name', 'provider'):
                if field_name in record._fields:
                    try:
                        value = record[field_name]
                    except Exception:
                        value = False
                    if value:
                        values.append(str(value))
        return ' '.join(values).lower()

    @api.model
    def _gl_filter_accounts_by_platform(self, accounts, platform):
        aliases = {
            'facebook': ('facebook', 'meta facebook'),
            'instagram': ('instagram', 'insta'),
        }
        needles = aliases.get(platform, (platform,))
        return accounts.filtered(
            lambda account: any(needle in self._gl_platform_search_text(account) for needle in needles)
        )

    def action_gl_post_instagram_now(self):
        self.ensure_one()
        return self._gl_retry_platform_now('instagram')

    def action_gl_post_facebook_now(self):
        self.ensure_one()
        return self._gl_retry_platform_now('facebook')

    def _gl_retry_platform_now(self, platform):
        """Create and immediately publish a platform-specific retry copy.

        A copy is intentional: Odoo's original social.post may already contain a
        successful live Facebook post and a failed Instagram live post. Reusing
        the original post through the standard publish action can publish again
        to every selected account. The retry copy contains only the selected
        platform account(s), so the successful platform is never duplicated.
        """
        self.ensure_one()
        if platform not in ('facebook', 'instagram'):
            raise UserError('Unbekannte Social-Media-Plattform.')

        accounts = self._gl_filter_accounts_by_platform(self._gl_target_accounts(), platform)
        platform_label = dict(self._fields['gl_retry_platform'].selection).get(platform, platform.title())
        if not accounts:
            raise UserError(
                'Für diesen Beitrag ist kein %s-Konto hinterlegt. Bitte prüfe im Feld „Posten auf“, '
                'ob der entsprechende Kanal ausgewählt ist.' % platform_label
            )

        now = fields.Datetime.now()
        defaults = {
            'gl_retry_source_post_id': self.id,
            'gl_retry_platform': platform,
            'gl_retry_attempted_at': now,
            'gl_auto_generated': False,
            'gl_requires_approval': False,
            'gl_approved': True,
            'gl_planned_date': False,
            'gl_latest_planned_date': False,
        }

        account_field_name = self._gl_account_field_name()
        if account_field_name:
            defaults[account_field_name] = [(6, 0, accounts.ids)]

        media_field = self._fields.get('media_ids')
        if media_field and getattr(media_field, 'comodel_name', '') == 'social.media':
            defaults['media_ids'] = [(6, 0, accounts.mapped('media_id').ids)]

        if 'scheduled_date' in self._fields:
            defaults['scheduled_date'] = now
        if 'published_date' in self._fields:
            defaults['published_date'] = False

        # Force the copied record into a direct/draft mode before calling the
        # native Odoo posting action. Selection keys vary slightly by release.
        if 'state' in self._fields:
            draft_state = self._gl_find_selection_key('state', ['draft', 'new'])
            if draft_state:
                defaults['state'] = draft_state
        if 'post_method' in self._fields:
            direct_method = self._gl_find_selection_key(
                'post_method', ['now', 'direct', 'send_now', 'immediate', 'post_now']
            )
            if direct_method:
                defaults['post_method'] = direct_method

        retry_post = self.sudo().copy(default=defaults)
        try:
            retry_post._gl_native_publish_now()
        except Exception:
            _logger.exception(
                'Direct %s retry failed for social.post %s (retry copy %s).',
                platform, self.id, retry_post.id,
            )
            raise

        try:
            self.message_post(
                body=(
                    'Direkter Wiederholungsversuch nur für <strong>%s</strong> wurde als '
                    'separater Social-Post #%s ausgelöst.'
                ) % (platform_label, retry_post.id)
            )
        except Exception:
            _logger.info(
                'Could not write retry note to social.post %s; retry post is %s.',
                self.id, retry_post.id,
            )

        return {
            'type': 'ir.actions.act_window',
            'name': '%s-Wiederholung' % platform_label,
            'res_model': 'social.post',
            'view_mode': 'form',
            'res_id': retry_post.id,
            'target': 'current',
        }

    def _gl_native_publish_now(self):
        """Call Odoo Social's native immediate publish method, bypassing our scheduler guard."""
        self.ensure_one()
        parent = super(SocialPost, self)
        for method_name in ('action_post', 'action_post_now', 'action_publish', '_action_post'):
            method = getattr(parent, method_name, None)
            if method:
                return method()
        raise UserError(
            'In dieser Odoo-Social-Version wurde keine native Direkt-Publishing-Methode gefunden.'
        )

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


    @api.model
    def _gl_repair_generated_media_links(self):
        """Repair inconsistent social.post account/media relations.

        Odoo groups social.live.post records by social.post.media_ids. If a
        live post references an account whose media is absent on the parent
        post, Odoo's compute method raises KeyError.
        """
        result = {'checked': 0, 'repaired': 0, 'without_accounts': 0, 'errors': 0}
        media_field = self._fields.get('media_ids')
        account_field_name = 'account_ids' if 'account_ids' in self._fields else ('social_account_ids' if 'social_account_ids' in self._fields else False)
        if not media_field or getattr(media_field, 'comodel_name', '') != 'social.media' or not account_field_name:
            return result

        posts = self.sudo().search([('gl_auto_generated', '=', True)])
        for post in posts:
            result['checked'] += 1
            try:
                accounts = post[account_field_name]
                media_ids = accounts.mapped('media_id').ids
                if not accounts:
                    result['without_accounts'] += 1
                if set(post.media_ids.ids) != set(media_ids):
                    post.with_context(gl_skip_groundlift_approval_hook=True).write({
                        'media_ids': [(6, 0, media_ids)],
                    })
                    result['repaired'] += 1
            except Exception:
                result['errors'] += 1
                _logger.exception('Could not repair social media links for social.post %s.', post.id)
        return result

    @api.model
    def _gl_media_commands_from_account_commands(self, account_commands):
        """Resolve social.media IDs from common many2many account commands."""
        if not account_commands:
            return False
        account_ids = []
        for command in account_commands:
            if not isinstance(command, (list, tuple)) or not command:
                continue
            if command[0] == 6 and len(command) >= 3:
                account_ids = list(command[2] or [])
            elif command[0] == 4 and len(command) >= 2:
                account_ids.append(command[1])
            elif command[0] == 5:
                account_ids = []
        if account_ids is None:
            return False
        media_ids = self.env['social.account'].sudo().browse(account_ids).mapped('media_id').ids
        return [(6, 0, media_ids)]

    @api.model_create_multi
    def create(self, vals_list):
        media_field = self._fields.get('media_ids')
        account_field_name = 'account_ids' if 'account_ids' in self._fields else ('social_account_ids' if 'social_account_ids' in self._fields else False)
        if media_field and getattr(media_field, 'comodel_name', '') == 'social.media' and account_field_name:
            for vals in vals_list:
                if vals.get('gl_auto_generated') and account_field_name in vals and 'media_ids' not in vals:
                    commands = self._gl_media_commands_from_account_commands(vals.get(account_field_name))
                    if commands is not False:
                        vals['media_ids'] = commands
        return super().create(vals_list)

    def write(self, vals):
        media_field = self._fields.get('media_ids')
        account_field_name = 'account_ids' if 'account_ids' in self._fields else ('social_account_ids' if 'social_account_ids' in self._fields else False)
        if media_field and getattr(media_field, 'comodel_name', '') == 'social.media' and account_field_name and account_field_name in vals and 'media_ids' not in vals and self.filtered('gl_auto_generated'):
            commands = self._gl_media_commands_from_account_commands(vals.get(account_field_name))
            if commands is not False:
                vals = dict(vals, media_ids=commands)
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
