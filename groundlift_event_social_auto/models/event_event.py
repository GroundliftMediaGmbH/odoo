# -*- coding: utf-8 -*-

import base64
import logging
import re
from io import BytesIO
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = ImageDraw = ImageFont = None
try:
    from odoo.tools.urls import url_join
except Exception:
    from urllib.parse import urljoin as url_join

_logger = logging.getLogger(__name__)


class EventEvent(models.Model):
    _inherit = 'event.event'

    gl_social_posts_generated = fields.Boolean(string='Groundlift Social Posts erzeugt', copy=False, index=True)
    gl_soldout_social_post_created = fields.Boolean(string='Groundlift Ausverkauft-Post erzeugt', copy=False, index=True)
    gl_completed_social_post_created = fields.Boolean(string='Groundlift Nachbericht-Post erzeugt', copy=False, index=True)
    gl_social_auto_publish_ok = fields.Boolean(string='Social Posts für diese Veranstaltung freigeben', copy=False)
    gl_social_post_ids = fields.One2many('social.post', 'gl_event_id', string='Groundlift Social Posts')
    gl_social_post_count = fields.Integer(string='Anzahl Social Posts', compute='_compute_gl_social_post_count')
    gl_social_last_error = fields.Text(string='Letzter Social-Automation-Hinweis', copy=False)

    @api.depends('gl_social_post_ids')
    def _compute_gl_social_post_count(self):
        for event in self:
            event.gl_social_post_count = len(event.gl_social_post_ids)

    def write(self, vals):
        result = super().write(vals)
        watched_stage_fields = {'stage_id', 'event_stage_id', 'state'}
        if watched_stage_fields.intersection(vals.keys()):
            self._gl_auto_create_social_posts_from_stage_change()
            self._gl_handle_completed_changes()
        if 'gl_social_auto_publish_ok' in vals and vals.get('gl_social_auto_publish_ok'):
            self.action_gl_approve_social_posts()
        if {'name', 'seats_available', 'seats_taken', 'seats_max', 'registration_ids', 'event_ticket_ids'}.intersection(vals.keys()):
            self._gl_handle_soldout_changes()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        events._gl_auto_create_social_posts_from_stage_change()
        return events

    def action_gl_create_social_posts(self):
        config = self.env['gl.event.social.config'].get_config()
        created = self._gl_create_social_posts(config=config, force=True, raise_on_error=True)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': 'Groundlift Social Automation', 'message': '%s Social Post(s) erzeugt.' % len(created), 'sticky': False, 'type': 'success'}}

    def action_gl_approve_social_posts(self):
        posts = self.mapped('gl_social_post_ids').filtered(lambda p: p.gl_requires_approval or not p.gl_approved)
        for post in posts:
            post.action_gl_approve_and_schedule()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': 'Groundlift Social Automation', 'message': '%s Social Post(s) freigegeben und geplant.' % len(posts), 'sticky': False, 'type': 'success'}}

    def action_gl_open_social_posts(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Social Posts: %s' % self.name, 'res_model': 'social.post', 'view_mode': 'list,form,calendar', 'domain': [('gl_event_id', '=', self.id)], 'context': {'default_gl_event_id': self.id}}

    @api.model
    def _cron_gl_event_social_automation(self):
        config = self.env['gl.event.social.config'].get_config()
        if not config.active:
            return True
        domain = [('gl_social_posts_generated', '=', False)]
        if 'date_begin' in self._fields:
            domain.append(('date_begin', '>', fields.Datetime.now()))
        self.search(domain, limit=150)._gl_auto_create_social_posts_from_stage_change(config=config)
        self.search([])._gl_handle_soldout_changes(config=config, limit=150)
        completed_domain = [('gl_completed_social_post_created', '=', False)]
        if 'date_end' in self._fields:
            completed_domain.append(('date_end', '<=', fields.Datetime.now()))
            completed_domain.append(('date_end', '>=', fields.Datetime.now() - timedelta(days=14)))
        self.search(completed_domain, limit=150)._gl_handle_completed_changes(config=config)
        config._gl_create_weekly_promo_posts(force_one=False)
        config._gl_create_gap_filler_posts(force_one=False)
        return True

    def _gl_auto_create_social_posts_from_stage_change(self, config=None):
        config = config or self.env['gl.event.social.config'].get_config()
        if not config.active:
            return self.env['social.post'].browse()
        target_events = self.filtered(lambda event: event._gl_is_in_announcement_stage(config))
        return target_events._gl_create_social_posts(config=config, force=False, raise_on_error=False)

    def _gl_is_in_announcement_stage(self, config):
        self.ensure_one()
        return self._gl_stage_matches(config.announcement_stage_name or 'Angekündigt')

    def _gl_is_in_completed_stage(self, config):
        self.ensure_one()
        if self._gl_stage_matches(config.completed_stage_name or 'Abgeschlossen'):
            return True
        if 'state' in self._fields:
            state = self._gl_normalize(str(self.state or ''))
            if state in ['done', 'closed', 'abgeschlossen', 'completed']:
                return True
        return False

    def _gl_stage_matches(self, target_name):
        self.ensure_one()
        target = self._gl_normalize(target_name or '')
        if not target:
            return False
        for field_name in ['stage_id', 'event_stage_id']:
            if field_name in self._fields:
                stage = self[field_name]
                if stage and self._gl_normalize(stage.name) == target:
                    return True
        if 'state' in self._fields and self._gl_normalize(str(self.state or '')) == target:
            return True
        return False

    def _gl_create_social_posts(self, config=None, force=False, raise_on_error=False, batch_mode=False):
        config = config or self.env['gl.event.social.config'].get_config()
        created_posts = self.env['social.post'].browse()
        accounts = config._get_social_accounts(raise_on_error=raise_on_error)
        if not accounts:
            self._gl_note_social_error('Keine passenden Facebook-/Instagram-Social-Accounts gefunden.')
            return created_posts
        for event in self:
            if not force and event.gl_social_posts_generated:
                continue
            if not event._gl_has_future_event_date():
                event._gl_note_social_error('Keine zukünftige Veranstaltung / kein gültiges Startdatum gefunden.')
                continue
            sold_out = event._gl_is_sold_out()
            post_specs = event._gl_build_post_specs(config, sold_out=sold_out, include_soldout=sold_out, batch_mode=batch_mode)
            for raw_spec in post_specs:
                existing = event.gl_social_post_ids.filtered(lambda p: p.gl_event_social_type == raw_spec['post_type'])
                if existing and not force:
                    continue
                spec = event._gl_apply_global_scheduling_rules(config, raw_spec)
                if not spec:
                    continue
                created_posts |= event._gl_create_one_social_post(config, accounts, spec, raise_on_error=raise_on_error)
            event.gl_social_posts_generated = True
            if sold_out:
                event.gl_soldout_social_post_created = True
                event._gl_adjust_future_posts_for_soldout(config=config)
        return created_posts

    def _gl_create_one_social_post(self, config, accounts, spec, raise_on_error=False):
        self.ensure_one()
        SocialPost = self.env['social.post'].sudo()
        vals = self._gl_prepare_social_post_vals(config, accounts, spec)
        try:
            post = SocialPost.create(vals)
            if not config.auto_post_without_approval and not self.gl_social_auto_publish_ok:
                post.write({'gl_requires_approval': True, 'gl_approved': False})
                post._gl_force_draft_if_possible()
            else:
                post.action_gl_approve_and_schedule()
            return post
        except Exception as exc:
            _logger.exception('Could not create social post for event %s.', self.id)
            self._gl_note_social_error(str(exc))
            if raise_on_error:
                raise UserError('Social Post konnte nicht erzeugt werden: %s' % exc)
            return SocialPost.browse()

    def _gl_prepare_social_post_vals(self, config, accounts, spec):
        self.ensure_one()
        SocialPost = self.env['social.post']
        post_fields = SocialPost._fields
        planned_date = spec['planned_date']
        message = spec['message']
        publication_kind = spec.get('publication_kind') or config.default_publication_kind or 'story'
        vals = {
            'gl_event_id': self.id,
            'gl_event_social_type': spec['post_type'],
            'gl_auto_generated': True,
            'gl_planned_date': planned_date,
            'gl_requires_approval': not (config.auto_post_without_approval or self.gl_social_auto_publish_ok),
            'gl_approved': bool(config.auto_post_without_approval or self.gl_social_auto_publish_ok),
            'gl_publication_kind': publication_kind,
            'gl_publish_as_feed_post': publication_kind == 'feed',
        }
        if spec.get('latest_planned_date'):
            vals['gl_latest_planned_date'] = spec['latest_planned_date']
        if 'message' in post_fields:
            vals['message'] = message
        elif 'message_deserialized' in post_fields:
            vals['message_deserialized'] = message
        elif 'body' in post_fields:
            vals['body'] = message
        if 'account_ids' in post_fields:
            vals['account_ids'] = [(6, 0, accounts.ids)]
        elif 'social_account_ids' in post_fields:
            vals['social_account_ids'] = [(6, 0, accounts.ids)]
        # Odoo Social expects the selected networks (social.media) to match the
        # media of the selected accounts. Without this, its
        # _compute_live_posts_by_media can crash with KeyError.
        media_field = post_fields.get('media_ids')
        if media_field and getattr(media_field, 'comodel_name', '') == 'social.media':
            vals['media_ids'] = [(6, 0, accounts.mapped('media_id').ids)]
        if 'scheduled_date' in post_fields:
            vals['scheduled_date'] = planned_date
        if 'post_method' in post_fields:
            scheduled_key = self.env['social.post']._gl_find_selection_key('post_method', ['scheduled', 'schedule', 'later', 'schedule_later'])
            if scheduled_key:
                vals['post_method'] = scheduled_key
        attachment = self._gl_create_event_image_attachment(sold_out=self._gl_is_sold_out(), publication_kind=publication_kind)
        if attachment:
            # media_ids is the list of social networks, not an attachment field.
            for image_field in ['image_ids', 'attachment_ids']:
                field = post_fields.get(image_field)
                if field and getattr(field, 'type', '') in ['many2many', 'one2many'] and getattr(field, 'comodel_name', '') == 'ir.attachment':
                    vals[image_field] = [(6, 0, [attachment.id])]
                    break
        if 'company_id' in post_fields and 'company_id' in self._fields and self.company_id:
            vals['company_id'] = self.company_id.id
        return vals

    def _gl_build_post_specs(self, config, sold_out=False, include_soldout=False, batch_mode=False):
        self.ensure_one()
        specs, now = [], fields.Datetime.now()
        first_dt, latest_first_dt = self._gl_announcement_datetime_window(config)
        if self._gl_should_create_planned_post(first_dt, now, config):
            specs.append({
                'post_type': 'announcement',
                'planned_date': first_dt,
                'latest_planned_date': latest_first_dt,
                'message': self._gl_render_post_message(config, 'announcement', sold_out=sold_out),
            })
        elif latest_first_dt and latest_first_dt <= now:
            self._gl_note_social_error(
                'Erstankündigung wurde nicht erzeugt, weil die Veranstaltung weniger als %s Tage entfernt ist.'
                % (config.announcement_min_days_before or 7)
            )
        if sold_out:
            if include_soldout and config.create_soldout_posts:
                soldout_dt = now + timedelta(hours=max(config.soldout_delay_hours or 1, 1))
                specs.append({'post_type': 'soldout', 'planned_date': soldout_dt, 'message': self._gl_render_post_message(config, 'soldout', sold_out=True)})
            event_day_type = 'event_day_soldout'
        else:
            reminder_dt = self._gl_event_relative_datetime(days_delta=-(config.reminder_days_before or 3), hour=config.reminder_hour, minute=config.reminder_minute, tzname=config.timezone)
            if self._gl_should_create_planned_post(reminder_dt, now, config):
                specs.append({'post_type': 'reminder_3d', 'planned_date': reminder_dt, 'message': self._gl_render_post_message(config, 'reminder_3d', sold_out=False)})
            event_day_type = 'event_day'
        event_day_dt = self._gl_event_relative_datetime(days_delta=0, hour=config.event_day_hour, minute=config.event_day_minute, tzname=config.timezone)
        if self._gl_should_create_planned_post(event_day_dt, now, config):
            specs.append({'post_type': event_day_type, 'planned_date': event_day_dt, 'message': self._gl_render_post_message(config, event_day_type, sold_out=sold_out)})
        return specs

    def _gl_announcement_datetime_window(self, config):
        """Return (desired_dt, latest_dt) for the first announcement.

        The first announcement should be created as early as possible, but never later
        than the configured minimum distance before the event. This prevents bulk imports
        and collision moves from pushing first announcements too close to the event date.
        """
        self.ensure_one()
        desired_dt = self._gl_next_day_datetime(config.first_post_hour, config.first_post_minute, config.timezone)
        min_days = max(config.announcement_min_days_before or 7, 0)
        latest_dt = self._gl_event_relative_datetime(days_delta=-min_days, hour=config.first_post_hour, minute=config.first_post_minute, tzname=config.timezone)
        if latest_dt and desired_dt and desired_dt > latest_dt:
            desired_dt = latest_dt
        return desired_dt, latest_dt

    def _gl_apply_global_scheduling_rules(self, config, spec):
        self.ensure_one()
        planned_dt = self._gl_resolve_planned_date_global(config, spec['planned_date'], spec['post_type'], latest_dt=spec.get('latest_planned_date'))
        if not planned_dt:
            if spec.get('latest_planned_date'):
                self._gl_note_social_error(
                    'Post %s wurde nicht geplant, weil vor der spätesten zulässigen Deadline kein freier Social-Tag gefunden wurde.'
                    % spec['post_type']
                )
            else:
                self._gl_note_social_error('Post %s wurde wegen eines höher priorisierten Posts am gleichen Tag übersprungen.' % spec['post_type'])
            return False
        result = dict(spec)
        result['planned_date'] = planned_dt
        return result

    @api.model
    def _gl_resolve_planned_date_global(self, config, desired_dt, post_type, latest_dt=None):
        if not desired_dt:
            return False
        if latest_dt and desired_dt > latest_dt:
            desired_dt = latest_dt
        if latest_dt and latest_dt <= fields.Datetime.now() and config.skip_past_planned_posts:
            return False
        priority = self._gl_post_priority(post_type)
        conflicts = self._gl_auto_posts_on_same_local_date(desired_dt, config.timezone).filtered(lambda p: not self._gl_is_post_record_published(p))
        if not conflicts:
            return desired_dt
        higher_or_equal = conflicts.filtered(lambda p: self._gl_post_priority(p.gl_event_social_type) >= priority)
        lower = conflicts - higher_or_equal
        if higher_or_equal:
            if self._gl_is_flexible_post_type(post_type):
                return self._gl_find_alternative_free_datetime(config, desired_dt + timedelta(days=1), latest_dt=latest_dt, fallback_before_dt=desired_dt - timedelta(days=1))
            return False
        for post in lower:
            if self._gl_is_flexible_post_type(post.gl_event_social_type):
                post_latest_dt = post.gl_latest_planned_date or False
                new_dt = self._gl_find_alternative_free_datetime(
                    config,
                    (post.gl_planned_date or desired_dt) + timedelta(days=1),
                    exclude_post_ids=[post.id],
                    latest_dt=post_latest_dt,
                    fallback_before_dt=(post.gl_planned_date or desired_dt) - timedelta(days=1),
                )
                if new_dt:
                    vals = {'gl_planned_date': new_dt}
                    if 'scheduled_date' in post._fields:
                        vals['scheduled_date'] = new_dt
                    post.sudo().write(vals)
                else:
                    if post.gl_event_id:
                        post.gl_event_id._gl_note_social_error('Ein niedriger priorisierter Post konnte wegen einer Kollision nicht rechtzeitig verschoben werden: %s' % (post.gl_event_social_type or 'unbekannt'))
                    try:
                        post.sudo().unlink()
                    except Exception:
                        _logger.exception('Could not remove lower-priority conflicting social.post %s.', post.id)
            else:
                try:
                    post.sudo().unlink()
                except Exception:
                    _logger.exception('Could not remove lower-priority conflicting social.post %s.', post.id)
        return desired_dt

    @api.model
    def _gl_find_next_free_datetime(self, config, start_dt, exclude_post_ids=None, latest_dt=None):
        exclude_post_ids = exclude_post_ids or []
        candidate = start_dt
        for _attempt in range(120):
            if latest_dt and candidate > latest_dt:
                return False
            conflicts = self._gl_auto_posts_on_same_local_date(candidate, config.timezone).filtered(lambda p: p.id not in exclude_post_ids and not self._gl_is_post_record_published(p))
            if not conflicts:
                return candidate
            candidate = candidate + timedelta(days=1)
        return False

    @api.model
    def _gl_find_previous_free_datetime(self, config, start_dt, exclude_post_ids=None, earliest_dt=None):
        exclude_post_ids = exclude_post_ids or []
        candidate = start_dt
        earliest_dt = earliest_dt or (fields.Datetime.now() + timedelta(minutes=5))
        for _attempt in range(120):
            if candidate < earliest_dt:
                return False
            conflicts = self._gl_auto_posts_on_same_local_date(candidate, config.timezone).filtered(lambda p: p.id not in exclude_post_ids and not self._gl_is_post_record_published(p))
            if not conflicts:
                return candidate
            candidate = candidate - timedelta(days=1)
        return False

    @api.model
    def _gl_find_alternative_free_datetime(self, config, preferred_start_dt, exclude_post_ids=None, latest_dt=None, fallback_before_dt=None):
        # Erst nach hinten schieben. Falls dadurch die Deadline überschritten würde,
        # rückwärts nach einem freien Tag suchen, damit flexible Erstankündigungen
        # trotzdem rechtzeitig vor der Veranstaltung nachgeholt werden können.
        candidate = self._gl_find_next_free_datetime(config, preferred_start_dt, exclude_post_ids=exclude_post_ids, latest_dt=latest_dt)
        if candidate:
            return candidate
        if latest_dt:
            start_back = min(fallback_before_dt or latest_dt, latest_dt)
            return self._gl_find_previous_free_datetime(config, start_back, exclude_post_ids=exclude_post_ids)
        return False

    @api.model
    def _gl_auto_posts_on_same_local_date(self, planned_dt, tzname):
        target_date = self._gl_local_date_from_utc(planned_dt, tzname)
        posts = self.env['social.post'].sudo().search([('gl_auto_generated', '=', True)], limit=2000)
        return posts.filtered(lambda p: self._gl_local_date_from_utc(p.gl_planned_date or ('scheduled_date' in p._fields and p.scheduled_date), tzname) == target_date)

    @api.model
    def _gl_post_priority(self, post_type):
        # Wöchentliche Werbeposts und Lückenfüller haben bewusst Vorrang vor
        # Erstankündigungen. Erstankündigungen bleiben flexibel, werden aber nur
        # bis zur konfigurierten Deadline verschoben. Eventtag/Reminder bleiben höher.
        return {
            'event_day_soldout': 105,
            'event_day': 100,
            'soldout': 90,
            'completed': 85,
            'reminder_3d': 80,
            'weekly_promo': 35,
            'gap_filler': 30,
            'announcement': 20,
        }.get(post_type or '', 10)

    @api.model
    def _gl_is_flexible_post_type(self, post_type):
        return post_type in ['announcement', 'gap_filler', 'weekly_promo']

    @api.model
    def _gl_is_post_record_published(self, post):
        if 'state' not in post._fields:
            return False
        return str(post.state or '').lower() in ['posted', 'published', 'done', 'sent']

    def _gl_handle_soldout_changes(self, config=None, limit=None):
        config = config or self.env['gl.event.social.config'].get_config()
        events = self[:limit] if limit else self
        for event in events:
            if not event.gl_social_posts_generated or not event._gl_is_sold_out() or event.gl_soldout_social_post_created or not config.create_soldout_posts:
                continue
            accounts = config._get_social_accounts(raise_on_error=False)
            if not accounts:
                event._gl_note_social_error('Ausverkauft erkannt, aber keine Social Accounts gefunden.')
                continue
            raw_spec = {'post_type': 'soldout', 'planned_date': fields.Datetime.now() + timedelta(hours=max(config.soldout_delay_hours or 1, 1)), 'message': event._gl_render_post_message(config, 'soldout', sold_out=True)}
            spec = event._gl_apply_global_scheduling_rules(config, raw_spec)
            if spec:
                event._gl_create_one_social_post(config, accounts, spec, raise_on_error=False)
                event.gl_soldout_social_post_created = True
                event._gl_adjust_future_posts_for_soldout(config=config)

    def _gl_adjust_future_posts_for_soldout(self, config=None):
        config = config or self.env['gl.event.social.config'].get_config()
        now = fields.Datetime.now()
        for event in self:
            future_posts = event.gl_social_post_ids.filtered(lambda p: not p.gl_planned_date or p.gl_planned_date > now)
            if config.delete_future_promo_when_soldout:
                removable = future_posts.filtered(lambda p: p.gl_event_social_type == 'reminder_3d' and not event._gl_is_post_published(p))
                if removable:
                    removable.unlink()
            event_day_posts = future_posts.filtered(lambda p: p.gl_event_social_type == 'event_day' and not event._gl_is_post_published(p))
            for post in event_day_posts:
                vals = {'gl_event_social_type': 'event_day_soldout', 'gl_requires_approval': not (config.auto_post_without_approval or event.gl_social_auto_publish_ok), 'gl_approved': bool(config.auto_post_without_approval or event.gl_social_auto_publish_ok)}
                msg = event._gl_render_post_message(config, 'event_day_soldout', sold_out=True)
                if 'message' in post._fields:
                    vals['message'] = msg
                elif 'message_deserialized' in post._fields:
                    vals['message_deserialized'] = msg
                elif 'body' in post._fields:
                    vals['body'] = msg
                source_attachment = False
                image_field = post._gl_attachment_field_name() if hasattr(post, '_gl_attachment_field_name') else False
                if image_field and hasattr(post, '_gl_image_attachments'):
                    source_attachment = post._gl_image_attachments()[:1]
                attachment = event._gl_create_event_image_attachment(
                    sold_out=True,
                    publication_kind=post.gl_publication_kind or config.default_publication_kind or 'story',
                    source_attachment=source_attachment,
                )
                if attachment and image_field:
                    vals[image_field] = [(6, 0, [attachment.id])]
                post.write(vals)

    def _gl_handle_completed_changes(self, config=None):
        config = config or self.env['gl.event.social.config'].get_config()
        accounts = config._get_social_accounts(raise_on_error=False)
        if not accounts:
            return self.env['social.post'].browse()
        created = self.env['social.post'].browse()
        for event in self:
            if event.gl_completed_social_post_created or not event._gl_is_in_completed_stage(config):
                continue
            raw_spec = {'post_type': 'completed', 'planned_date': event._gl_next_day_datetime(config.completed_post_hour, config.completed_post_minute, config.timezone), 'message': event._gl_render_post_message(config, 'completed', sold_out=False)}
            spec = event._gl_apply_global_scheduling_rules(config, raw_spec)
            if spec:
                post = event._gl_create_one_social_post(config, accounts, spec, raise_on_error=False)
                created |= post
                event.gl_completed_social_post_created = bool(post)
        return created

    def _gl_render_post_message(self, config, post_type, sold_out=False, extra_instruction=''):
        self.ensure_one()
        title = self.name or 'Veranstaltung im Groundlift Studio'
        date_text = self._gl_format_event_datetime(config.timezone)
        description = self._gl_short_description(max_chars=900)
        ticket_url = self._gl_event_ticket_url()
        hashtags = self._gl_hashtags(config)
        extra_instruction = self._gl_clean_event_description_text(extra_instruction, max_chars=500) if extra_instruction else ''
        fallback_headline = self._gl_fallback_headline(config, post_type, sold_out=sold_out)
        headline = config._gl_openai_generate_headline_for_event(self, post_type, fallback_headline, sold_out=sold_out) or fallback_headline

        def join(parts):
            return '\n\n'.join([p for p in parts if p])

        def headline_with_link(headline_value, link_value):
            # Der Ticketlink soll direkt unter der Überschrift stehen, ohne Titel/Datum dazwischen.
            # Zwischen Headline und Link wird nur ein einfacher Zeilenumbruch gesetzt.
            if headline_value and link_value:
                return '%s\n%s' % (headline_value, link_value)
            return headline_value or link_value or ''

        # Für Nachberichte wird kein Ticketlink gesetzt, da die Veranstaltung bereits vorbei ist.
        headline_block = headline_with_link(headline, ticket_url)
        if post_type == 'announcement':
            parts = [headline_block, title, date_text, description, extra_instruction, hashtags]
            return join(parts)
        if post_type == 'reminder_3d':
            parts = [headline_block, title, date_text, description, extra_instruction, hashtags]
            return join(parts)
        if post_type == 'event_day':
            parts = [headline_block, title, date_text, description, extra_instruction, hashtags]
            return join(parts)
        if post_type == 'soldout':
            parts = [headline_block, title, date_text, 'Wir freuen uns auf einen besonderen Abend bei uns in der Alten Brauerei Stegen.', hashtags]
            return join(parts)
        if post_type == 'event_day_soldout':
            parts = [headline_block, title, date_text, 'Danke an alle, die dabei sind. Wir freuen uns auf euch im Groundlift Studio.', hashtags]
            return join(parts)
        if post_type == 'completed':
            parts = [headline, title, config.body_completed or 'Postet gerne in die Kommentare und Bilder, wie es für euch war!', extra_instruction, hashtags]
            return join(parts)
        return join([headline_block, title, date_text, hashtags])

    def _gl_fallback_headline(self, config, post_type, sold_out=False):
        if post_type == 'announcement':
            if sold_out:
                return 'Neu angekündigt – bereits ausverkauft:'
            return config.headline_announcement or 'Neu angekündigt im Groundlift Studio:'
        if post_type == 'reminder_3d':
            return config.headline_reminder or 'In 3 Tagen bei uns:'
        if post_type == 'event_day':
            return config.headline_event_day or 'Heute im Groundlift Studio:'
        if post_type == 'soldout':
            return config.headline_soldout or 'Ausverkauft – danke für euer riesiges Interesse!'
        if post_type == 'event_day_soldout':
            return config.headline_event_day_soldout or 'Heute vor vollem Haus:'
        if post_type == 'completed':
            return config.headline_completed or 'Schön, dass ihr da wart!'
        return 'Groundlift Studio:'

    def _gl_short_description(self, max_chars=900):
        self.ensure_one()
        description = ''
        for field_name in ['x_studio_html_field_eventbeschreibung', 'subtitle', 'website_description', 'description', 'note']:
            if field_name in self._fields and self[field_name]:
                description = self[field_name]
                break
        if not description:
            return ''
        return self._gl_clean_event_description_text(description, max_chars=max_chars)

    def _gl_clean_event_description_text(self, description, max_chars=900):
        """Return social-ready plain text while preserving useful paragraph breaks.

        Earlier versions compressed the HTML description into one long line.
        For social posts this looks cramped, especially when the event page has
        a short intro/teaser followed by the actual body text.
        """
        text = html2plaintext(description or '')
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'[ \t]+', ' ', text)
        raw_lines = [line.strip() for line in text.split('\n')]
        paragraphs, buffer = [], []
        for line in raw_lines:
            if line:
                buffer.append(line)
            elif buffer:
                paragraphs.append(' '.join(buffer).strip())
                buffer = []
        if buffer:
            paragraphs.append(' '.join(buffer).strip())
        paragraphs = [re.sub(r'\s+', ' ', p).strip() for p in paragraphs if p and p.strip()]
        if not paragraphs:
            paragraphs = [re.sub(r'\s+', ' ', html2plaintext(description or '')).strip()]

        # If the source HTML still collapsed to a single paragraph, create a
        # readable break after a concise opener such as "Ein Blick hinter ...".
        if len(paragraphs) == 1:
            paragraphs = self._gl_split_single_description_paragraph(paragraphs[0])

        text = '\n\n'.join([p for p in paragraphs if p])
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        if max_chars and len(text) > max_chars:
            text = text[:max_chars].rsplit(' ', 1)[0].rstrip('.,;:') + ' …'
        return text

    def _gl_split_single_description_paragraph(self, paragraph):
        paragraph = re.sub(r'\s+', ' ', paragraph or '').strip()
        if not paragraph:
            return []
        # Prefer splitting after the first real sentence.
        match = re.match(r'(.{45,220}?[.!?])\s+(.+)$', paragraph)
        if match:
            return [match.group(1).strip(), match.group(2).strip()]
        # Common event-page pattern: a short teaser/headline followed by body text.
        match = re.match(r'(.{35,180}?)(\s+(?:Bei|Mit|Nach|Freut|Freuen|Erlebt|Entdeckt|Taucht|Kommt|Wir)\s+.+)$', paragraph)
        if match:
            first = match.group(1).strip().rstrip('.,;:')
            second = match.group(2).strip()
            if first and second and len(first) >= 25:
                return [first, second]
        return [paragraph]

    def _gl_event_ticket_url(self):
        self.ensure_one()
        base = self.get_base_url() if hasattr(self, 'get_base_url') else self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        if 'website_url' in self._fields and self.website_url:
            path = self.website_url
        elif 'website_slug' in self._fields and self.website_slug:
            path = '/event/%s/register' % self.website_slug
        else:
            path = '/event/%s/register' % self.id
        try:
            return url_join(base, path)
        except Exception:
            return '%s%s' % (base.rstrip('/'), path if str(path).startswith('/') else '/' + str(path))

    def _gl_hashtags(self, config):
        self.ensure_one()
        tags = []
        if config.default_hashtags:
            tags.extend([tag.strip() for tag in config.default_hashtags.split() if tag.strip()])
        event_tag_records = self.env['event.tag'].browse()
        for field_name in ['tag_ids', 'event_tag_ids']:
            if field_name in self._fields and self[field_name]:
                event_tag_records |= self[field_name]
        for tag in event_tag_records:
            hashtag = self._gl_make_hashtag(tag.name)
            if hashtag:
                tags.append(hashtag)
        for field_name in ['event_type_id', 'x_studio_public_category', 'x_studio_website_kategorie']:
            if field_name in self._fields and self[field_name]:
                value = self[field_name]
                name = getattr(value, 'name', False) or str(value)
                hashtag = self._gl_make_hashtag(name)
                if hashtag:
                    tags.append(hashtag)
        api_hashtags = config._gl_openai_generate_hashtags_for_event(self, ' '.join(tags))
        if api_hashtags:
            tags.extend([tag.strip() for tag in api_hashtags.split() if tag.strip()])
        filtered = self._gl_filter_hashtags_for_event_context(tags)
        deduped, seen = [], set()
        for tag in filtered:
            if tag.lower() in seen:
                continue
            seen.add(tag.lower())
            deduped.append(tag)
        return ' '.join(deduped)

    def _gl_filter_hashtags_for_event_context(self, tags):
        self.ensure_one()
        context = self._gl_hashtag_context_text()
        result = []
        for tag in tags or []:
            clean = str(tag or '').strip()
            if not clean:
                continue
            normalized = clean.lower().replace('#', '')
            # Inventory-/Ticket-Hashtags nur verwenden, wenn sie wirklich im Eventkontext vorkommen.
            if any(token in normalized for token in ['stehplatz', 'sitzplatz', 'ticket', 'tiket', 'vorverkauf', 'vvk']):
                if not any(token in context for token in ['stehplatz', 'sitzplatz', 'ticket', 'tickets', 'vorverkauf', 'vvk']):
                    continue
            # #livemusik ist gut für Konzerte, aber falsch für Kabarett/Talk/Comedy ohne Musikbezug.
            if normalized in ['livemusik', 'liveband', 'konzert', 'band']:
                if not any(token in context for token in ['konzert', 'musik', 'musiker', 'band', 'jazz', 'rock', 'pop', 'singer', 'songwriter', 'piano', 'klavier', 'gitarre', 'bühne', 'buehne']):
                    continue
            result.append(clean)
        return result

    def _gl_hashtag_context_text(self):
        self.ensure_one()
        # Nur redaktioneller Event-Kontext. Event-/Ticket-Tags werden hier absichtlich
        # nicht einbezogen, weil sonst interne Kategorien wie 'Stehplatzticket' ihre
        # eigenen unpassenden Hashtags legitimieren würden.
        parts = [self.name or '', self._gl_short_description(max_chars=1600)]
        for field_name in ['event_type_id', 'x_studio_public_category', 'x_studio_website_kategorie']:
            if field_name in self._fields and self[field_name]:
                value = self[field_name]
                parts.append(getattr(value, 'name', False) or str(value))
        text = ' '.join([p for p in parts if p]).lower()
        return text.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')

    def _gl_make_hashtag(self, value):
        value = (value or '').strip().lower()
        for src, dst in {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'}.items():
            value = value.replace(src, dst)
        value = re.sub(r'[^a-z0-9]+', '', value)
        return '#' + value if value else ''

    def _gl_format_event_datetime(self, tzname='Europe/Berlin'):
        self.ensure_one()
        if 'date_begin' not in self._fields or not self.date_begin:
            return ''
        tz = pytz.timezone(tzname or 'Europe/Berlin')
        date_begin = fields.Datetime.from_string(self.date_begin)
        local_start = pytz.UTC.localize(date_begin).astimezone(tz) if date_begin.tzinfo is None else date_begin.astimezone(tz)
        date_part, time_part = local_start.strftime('%d.%m.%Y'), local_start.strftime('%H:%M')
        if 'date_end' in self._fields and self.date_end:
            date_end = fields.Datetime.from_string(self.date_end)
            local_end = pytz.UTC.localize(date_end).astimezone(tz) if date_end.tzinfo is None else date_end.astimezone(tz)
            if local_end.date() == local_start.date():
                return '%s · %s–%s Uhr' % (date_part, time_part, local_end.strftime('%H:%M'))
        return '%s · %s Uhr' % (date_part, time_part)

    def _gl_create_event_image_attachment(self, sold_out=False, publication_kind='story', source_attachment=False):
        self.ensure_one()
        field_name = 'x_studio_website_header'
        source_token = ''

        if source_attachment and source_attachment.datas:
            # Used when an already-created post is converted to sold out. In that
            # case the post image may already have been cropped manually or by the
            # module. The sold-out badge must be rendered on this visible image,
            # not on the original event header, otherwise the subsequent crop can
            # cut the badge off.
            data = source_attachment.datas
            source_token = '_src%s' % source_attachment.id
        else:
            if field_name not in self._fields:
                self._gl_note_social_error('Bildfeld x_studio_website_header existiert auf event.event nicht; kein Social-Bild angehängt.')
                return False
            data = self[field_name]
            if not data:
                self._gl_note_social_error('Bildfeld x_studio_website_header ist leer; kein Social-Bild angehängt.')
                return False

        if isinstance(data, str):
            data = data.encode()
        try:
            decoded = base64.b64decode(data, validate=False)
        except Exception:
            self._gl_note_social_error('Das Social-Bild enthält keine gültigen Bilddaten; kein Social-Bild angehängt.')
            return False

        normalized_kind = publication_kind or 'story'
        soldout_config = self.env['gl.event.social.config'].get_config() if sold_out else False
        if sold_out:
            badge_token = self._gl_soldout_badge_cache_token(soldout_config)
            suffix = '_%s_soldout_adjusted_overlay%s%s' % (normalized_kind, source_token, badge_token)
        else:
            suffix = ''
        filename = '%s_website_header_social%s.jpg' % (self._gl_filename_safe(self.name or 'event'), suffix)
        existing = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'event.event'),
            ('res_id', '=', self.id),
            ('name', '=', filename)
        ], limit=1)
        if existing:
            return existing

        final_data = data
        mimetype = 'image/jpeg'
        if sold_out:
            try:
                visible_image = self._gl_prepare_image_for_soldout_badge(decoded, publication_kind=normalized_kind)
                final_data = base64.b64encode(self._gl_add_soldout_badge_to_image(visible_image, publication_kind=normalized_kind, config=soldout_config))
            except Exception:
                _logger.exception('Could not render sold-out badge for event %s.', self.id)
                final_data = data
        return self.env['ir.attachment'].sudo().create({
            'name': filename,
            'type': 'binary',
            'datas': final_data,
            'res_model': 'event.event',
            'res_id': self.id,
            'mimetype': mimetype,
        })

    def _gl_prepare_image_for_soldout_badge(self, image_bytes, publication_kind='story'):
        """Return the visible social image bytes before the sold-out badge is drawn.

        The badge must be applied after the image has the ratio that this module
        will use for the post. Otherwise the image adjustment hook can crop the
        badge away after it has been rendered. Already suitable images are left
        unchanged.
        """
        if not Image:
            return image_bytes
        target_ratio = self._gl_social_target_aspect_ratio(publication_kind=publication_kind)
        if not target_ratio:
            return image_bytes
        with Image.open(BytesIO(image_bytes)) as image:
            image = image.convert('RGB')
            width, height = image.size
            current_ratio = float(width) / float(height or 1)
            if self._gl_social_ratio_is_acceptable(current_ratio, publication_kind=publication_kind):
                output = BytesIO()
                image.save(output, format='JPEG', quality=95)
                return output.getvalue()
            image = self._gl_pil_cover_crop_to_ratio(image, target_ratio)
            output = BytesIO()
            image.save(output, format='JPEG', quality=95)
            return output.getvalue()

    def _gl_social_target_aspect_ratio(self, publication_kind='story'):
        if (publication_kind or 'story') == 'story':
            return 9.0 / 16.0
        # For mixed Facebook/Instagram feed posts 4:5 is the safest vertical
        # target when a crop is necessary. Already acceptable feed images are
        # not cropped by _gl_prepare_image_for_soldout_badge.
        return 4.0 / 5.0

    def _gl_social_ratio_is_acceptable(self, ratio, publication_kind='story'):
        if not ratio:
            return False
        if (publication_kind or 'story') == 'story':
            return abs(ratio - (9.0 / 16.0)) <= 0.035
        return 0.79 <= ratio <= 1.92

    def _gl_pil_cover_crop_to_ratio(self, image, target_ratio):
        if not image or not target_ratio:
            return image
        width, height = image.size
        current_ratio = float(width) / float(height or 1)
        if abs(current_ratio - target_ratio) <= 0.001:
            return image
        if current_ratio > target_ratio:
            new_width = int(height * target_ratio)
            left = int((width - new_width) / 2)
            box = (max(left, 0), 0, min(left + new_width, width), height)
        else:
            new_height = int(width / target_ratio)
            top = int((height - new_height) / 2)
            box = (0, max(top, 0), width, min(top + new_height, height))
        return image.crop(box)

    def _gl_soldout_badge_cache_token(self, config=None):
        """Return a filename suffix so changed custom badges do not reuse old attachments."""
        if not config or not getattr(config, 'soldout_badge_png', False):
            return ''
        raw_stamp = str(config.write_date or fields.Datetime.now())
        stamp = re.sub(r'\D+', '', raw_stamp)[:14] or 'custom'
        return '_badge%s_%s' % (config.id, stamp)

    def _gl_add_soldout_badge_to_image(self, image_bytes, publication_kind='story', config=None):
        if not Image:
            return image_bytes
        custom_badge = self._gl_custom_soldout_badge_bytes(config=config)
        if custom_badge:
            try:
                return self._gl_overlay_custom_soldout_badge(image_bytes, custom_badge, publication_kind=publication_kind)
            except Exception:
                _logger.exception('Could not render custom sold-out PNG badge for event %s. Falling back to text badge.', self.id)
        if not ImageDraw:
            return image_bytes
        with Image.open(BytesIO(image_bytes)) as image:
            image = image.convert('RGBA')
            width, height = image.size
            overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            label = 'AUSVERKAUFT'
            font_size = max(34, int(min(width, height) * 0.085))
            font = self._gl_badge_font(font_size)
            try:
                bbox = draw.textbbox((0, 0), label, font=font)
                text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                text_w, text_h = draw.textsize(label, font=font)
            pad_x = int(text_w * 0.28)
            pad_y = int(text_h * 0.45)
            box_w = text_w + pad_x * 2
            box_h = text_h + pad_y * 2
            margin = int(min(width, height) * 0.055)
            x2 = width - margin
            y1 = margin
            x1 = max(margin, x2 - box_w)
            y2 = y1 + box_h
            try:
                draw.rounded_rectangle((x1, y1, x2, y2), radius=int(box_h * 0.22), fill=(210, 0, 0, 230), outline=(255, 255, 255, 245), width=max(3, int(box_h * 0.045)))
            except Exception:
                draw.rectangle((x1, y1, x2, y2), fill=(210, 0, 0, 230), outline=(255, 255, 255, 245))
            text_x = x1 + (box_w - text_w) / 2
            text_y = y1 + (box_h - text_h) / 2 - int(text_h * 0.08)
            draw.text((text_x, text_y), label, fill=(255, 255, 255, 255), font=font)
            image = Image.alpha_composite(image, overlay).convert('RGB')
            output = BytesIO()
            image.save(output, format='JPEG', quality=95)
            return output.getvalue()

    def _gl_custom_soldout_badge_bytes(self, config=None):
        config = config or self.env['gl.event.social.config'].get_config()
        badge_data = getattr(config, 'soldout_badge_png', False) if config else False
        if not badge_data:
            return False
        if isinstance(badge_data, str):
            badge_data = badge_data.encode()
        try:
            return base64.b64decode(badge_data, validate=False)
        except Exception:
            _logger.exception('Configured sold-out badge PNG contains invalid binary data.')
            return False

    def _gl_overlay_custom_soldout_badge(self, image_bytes, badge_bytes, publication_kind='story'):
        with Image.open(BytesIO(image_bytes)) as image, Image.open(BytesIO(badge_bytes)) as badge:
            image = image.convert('RGBA')
            badge = badge.convert('RGBA')
            width, height = image.size
            badge_w, badge_h = badge.size
            if not badge_w or not badge_h:
                return image_bytes

            # Keep the user-provided PNG fully inside the already-cropped social
            # image. This prevents the visible sticker from being cut off later.
            margin = max(12, int(min(width, height) * 0.055))
            max_w = max(1, int(width * 0.42))
            max_h = max(1, int(height * (0.16 if (publication_kind or 'story') == 'story' else 0.22)))
            scale = min(float(max_w) / float(badge_w), float(max_h) / float(badge_h), 1.0)
            new_w = max(1, int(badge_w * scale))
            new_h = max(1, int(badge_h * scale))
            if (new_w, new_h) != (badge_w, badge_h):
                resampling = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', Image.BICUBIC)
                badge = badge.resize((new_w, new_h), resampling)

            x = max(margin, width - margin - new_w)
            y = margin
            overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
            overlay.alpha_composite(badge, (x, y))
            result = Image.alpha_composite(image, overlay).convert('RGB')
            output = BytesIO()
            result.save(output, format='JPEG', quality=95)
            return output.getvalue()

    def _gl_badge_font(self, font_size):
        if not ImageFont:
            return None
        for path in (
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
            '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
        ):
            try:
                return ImageFont.truetype(path, font_size)
            except Exception:
                continue
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _gl_filename_safe(self, value):
        return re.sub(r'[^A-Za-z0-9_.-]+', '_', value).strip('_')[:80]

    def _gl_title_marks_sold_out(self):
        self.ensure_one()
        name = (self.name or '').strip()
        return bool(re.search(r'\(\s*ausverkauft\s*\)\s*$', name, flags=re.IGNORECASE))

    def _gl_is_sold_out(self):
        self.ensure_one()
        if self._gl_title_marks_sold_out():
            return True
        if 'seats_available' in self._fields and 'seats_max' in self._fields:
            try:
                if self.seats_max and self.seats_available <= 0:
                    return True
            except Exception:
                pass
        if 'seats_taken' in self._fields and 'seats_max' in self._fields:
            try:
                if self.seats_max and self.seats_taken >= self.seats_max:
                    return True
            except Exception:
                pass
        if 'event_ticket_ids' in self._fields and self.event_ticket_ids:
            limited_tickets = self.event_ticket_ids.filtered(lambda t: 'seats_max' in t._fields and t.seats_max)
            if limited_tickets:
                soldout_tickets = limited_tickets.filtered(lambda t: ('seats_available' in t._fields and t.seats_available <= 0) or ('seats_taken' in t._fields and t.seats_taken >= t.seats_max))
                return len(soldout_tickets) == len(limited_tickets)
        return False

    def _gl_is_post_published(self, post):
        return self._gl_is_post_record_published(post)

    def _gl_has_future_event_date(self):
        self.ensure_one()
        return 'date_begin' in self._fields and self.date_begin and self.date_begin > fields.Datetime.now()

    def _gl_next_day_datetime(self, hour, minute, tzname):
        tz = pytz.timezone(tzname or 'Europe/Berlin')
        now_local = pytz.UTC.localize(fields.Datetime.now()).astimezone(tz)
        local_dt = datetime.combine(now_local.date() + timedelta(days=1), time(max(min(hour or 0, 23), 0), max(min(minute or 0, 59), 0)))
        return self._gl_local_naive_to_utc_naive(local_dt, tz)

    def _gl_event_relative_datetime(self, days_delta, hour, minute, tzname):
        self.ensure_one()
        if 'date_begin' not in self._fields or not self.date_begin:
            return False
        tz = pytz.timezone(tzname or 'Europe/Berlin')
        date_begin = fields.Datetime.from_string(self.date_begin)
        local_start = pytz.UTC.localize(date_begin).astimezone(tz) if date_begin.tzinfo is None else date_begin.astimezone(tz)
        local_dt = datetime.combine(local_start.date() + timedelta(days=days_delta), time(max(min(hour or 0, 23), 0), max(min(minute or 0, 59), 0)))
        return self._gl_local_naive_to_utc_naive(local_dt, tz)

    def _gl_local_naive_to_utc_naive(self, local_dt, tz):
        return self._gl_local_naive_to_utc_naive_global(local_dt, tz)

    @api.model
    def _gl_local_naive_to_utc_naive_global(self, local_dt, tz):
        localized = tz.localize(local_dt) if local_dt.tzinfo is None else local_dt.astimezone(tz)
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    @api.model
    def _gl_local_date_from_utc(self, utc_dt, tzname='Europe/Berlin'):
        if not utc_dt:
            return False
        tz = pytz.timezone(tzname or 'Europe/Berlin')
        dt = fields.Datetime.from_string(utc_dt) if isinstance(utc_dt, str) else utc_dt
        if not dt:
            return False
        local_dt = pytz.UTC.localize(dt).astimezone(tz) if dt.tzinfo is None else dt.astimezone(tz)
        return local_dt.date()

    def _gl_should_create_planned_post(self, planned_dt, now, config):
        return bool(planned_dt and not (config.skip_past_planned_posts and planned_dt <= now))

    def _gl_update_social_generated_flags(self):
        for event in self:
            posts = event.gl_social_post_ids
            event.gl_social_posts_generated = bool(posts.filtered(lambda p: p.gl_event_social_type in ['announcement', 'reminder_3d', 'event_day', 'event_day_soldout', 'soldout']))
            event.gl_soldout_social_post_created = bool(posts.filtered(lambda p: p.gl_event_social_type == 'soldout'))
            event.gl_completed_social_post_created = bool(posts.filtered(lambda p: p.gl_event_social_type == 'completed'))

    def _gl_note_social_error(self, message):
        for event in self:
            event.gl_social_last_error = message
            if hasattr(event, 'message_post'):
                try:
                    event.message_post(body='Groundlift Social Automation: %s' % message)
                except Exception:
                    pass

    def _gl_normalize(self, value):
        value = (value or '').strip().lower()
        value = value.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
        return re.sub(r'\s+', ' ', value)
