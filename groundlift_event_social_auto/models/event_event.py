# -*- coding: utf-8 -*-

import base64
import logging
import re
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
try:
    from odoo.tools.urls import url_join
except Exception:  # pragma: no cover - older/newer Odoo fallback
    from urllib.parse import urljoin as url_join

_logger = logging.getLogger(__name__)


class EventEvent(models.Model):
    _inherit = 'event.event'

    gl_social_posts_generated = fields.Boolean(string='Groundlift Social Posts erzeugt', copy=False, index=True)
    gl_soldout_social_post_created = fields.Boolean(string='Groundlift Ausverkauft-Post erzeugt', copy=False, index=True)
    gl_social_auto_publish_ok = fields.Boolean(
        string='Social Posts für diese Veranstaltung freigeben',
        copy=False,
        help='Wenn aktiviert, werden die automatisch erzeugten Posts dieser Veranstaltung geplant.',
    )
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
        if 'gl_social_auto_publish_ok' in vals and vals.get('gl_social_auto_publish_ok'):
            self.action_gl_approve_social_posts()
        # If relevant attendance fields changed, check for sold out.
        if {'seats_available', 'seats_taken', 'seats_max', 'registration_ids'}.intersection(vals.keys()):
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
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Groundlift Social Automation',
                'message': '%s Social Post(s) erzeugt.' % len(created),
                'sticky': False,
                'type': 'success',
            },
        }

    def action_gl_approve_social_posts(self):
        posts = self.mapped('gl_social_post_ids').filtered(lambda p: p.gl_requires_approval or not p.gl_approved)
        for post in posts:
            post.action_gl_approve_and_schedule()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Groundlift Social Automation',
                'message': '%s Social Post(s) freigegeben und geplant.' % len(posts),
                'sticky': False,
                'type': 'success',
            },
        }

    def action_gl_open_social_posts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Social Posts: %s' % self.name,
            'res_model': 'social.post',
            'view_mode': 'list,form,calendar',
            'domain': [('gl_event_id', '=', self.id)],
            'context': {'default_gl_event_id': self.id},
        }

    @api.model
    def _cron_gl_event_social_automation(self):
        config = self.env['gl.event.social.config'].get_config()
        if not config.active:
            return True

        domain = [('gl_social_posts_generated', '=', False)]
        events = self.search(domain, limit=100)
        events._gl_auto_create_social_posts_from_stage_change(config=config)
        self.search([])._gl_handle_soldout_changes(config=config, limit=150)
        return True

    def _gl_auto_create_social_posts_from_stage_change(self, config=None):
        config = config or self.env['gl.event.social.config'].get_config()
        if not config.active:
            return self.env['social.post'].browse()
        target_events = self.filtered(lambda event: event._gl_is_in_announcement_stage(config))
        return target_events._gl_create_social_posts(config=config, force=False, raise_on_error=False)

    def _gl_is_in_announcement_stage(self, config):
        self.ensure_one()
        target = self._gl_normalize(config.announcement_stage_name or 'Angekündigt')
        for field_name in ['stage_id', 'event_stage_id']:
            if field_name in self._fields:
                stage = self[field_name]
                if stage and self._gl_normalize(stage.name) == target:
                    return True
        if 'state' in self._fields and self._gl_normalize(str(self.state or '')) == target:
            return True
        return False

    def _gl_create_social_posts(self, config=None, force=False, raise_on_error=False):
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
            post_specs = event._gl_build_post_specs(config, sold_out=sold_out, include_soldout=sold_out)
            for spec in post_specs:
                existing = event.gl_social_post_ids.filtered(lambda p: p.gl_event_social_type == spec['post_type'])
                if existing and not force:
                    continue
                post = event._gl_create_one_social_post(config, accounts, spec, raise_on_error=raise_on_error)
                created_posts |= post

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
        vals = {
            'gl_event_id': self.id,
            'gl_event_social_type': spec['post_type'],
            'gl_auto_generated': True,
            'gl_planned_date': planned_date,
            'gl_requires_approval': not (config.auto_post_without_approval or self.gl_social_auto_publish_ok),
            'gl_approved': bool(config.auto_post_without_approval or self.gl_social_auto_publish_ok),
        }

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

        if 'scheduled_date' in post_fields:
            vals['scheduled_date'] = planned_date
        if 'post_method' in post_fields:
            # Keep the record configured for scheduling even if approval is still required.
            scheduled_key = self.env['social.post']._gl_find_selection_key('post_method', ['scheduled', 'schedule', 'later', 'schedule_later'])
            if scheduled_key:
                vals['post_method'] = scheduled_key

        attachment = self._gl_create_event_image_attachment()
        if attachment:
            for image_field in ['image_ids', 'attachment_ids', 'media_ids']:
                if image_field in post_fields:
                    field = post_fields[image_field]
                    if getattr(field, 'type', '') in ['many2many', 'one2many']:
                        vals[image_field] = [(6, 0, [attachment.id])]
                        break

        # If the social.post model exposes company_id, set it from the event when possible.
        if 'company_id' in post_fields and 'company_id' in self._fields and self.company_id:
            vals['company_id'] = self.company_id.id

        return vals

    def _gl_build_post_specs(self, config, sold_out=False, include_soldout=False):
        self.ensure_one()
        specs = []
        now = fields.Datetime.now()

        first_dt = self._gl_next_day_datetime(config.first_post_hour, config.first_post_minute, config.timezone)
        if self._gl_should_create_planned_post(first_dt, now, config):
            specs.append({
                'post_type': 'announcement',
                'planned_date': first_dt,
                'message': self._gl_render_post_message(config, 'announcement', sold_out=sold_out),
            })

        if sold_out:
            if include_soldout and config.create_soldout_posts:
                soldout_dt = now + timedelta(hours=max(config.soldout_delay_hours or 1, 1))
                specs.append({
                    'post_type': 'soldout',
                    'planned_date': soldout_dt,
                    'message': self._gl_render_post_message(config, 'soldout', sold_out=True),
                })
            event_day_type = 'event_day_soldout'
        else:
            reminder_dt = self._gl_event_relative_datetime(
                days_delta=-(config.reminder_days_before or 3),
                hour=config.reminder_hour,
                minute=config.reminder_minute,
                tzname=config.timezone,
            )
            if self._gl_should_create_planned_post(reminder_dt, now, config):
                specs.append({
                    'post_type': 'reminder_3d',
                    'planned_date': reminder_dt,
                    'message': self._gl_render_post_message(config, 'reminder_3d', sold_out=False),
                })
            event_day_type = 'event_day'

        event_day_dt = self._gl_event_relative_datetime(
            days_delta=0,
            hour=config.event_day_hour,
            minute=config.event_day_minute,
            tzname=config.timezone,
        )
        if self._gl_should_create_planned_post(event_day_dt, now, config):
            specs.append({
                'post_type': event_day_type,
                'planned_date': event_day_dt,
                'message': self._gl_render_post_message(config, event_day_type, sold_out=sold_out),
            })
        return specs

    def _gl_handle_soldout_changes(self, config=None, limit=None):
        config = config or self.env['gl.event.social.config'].get_config()
        events = self
        if limit:
            events = events[:limit]
        for event in events:
            if not event.gl_social_posts_generated:
                continue
            if not event._gl_is_sold_out() or event.gl_soldout_social_post_created:
                continue
            if not config.create_soldout_posts:
                continue
            accounts = config._get_social_accounts(raise_on_error=False)
            if not accounts:
                event._gl_note_social_error('Ausverkauft erkannt, aber keine Social Accounts gefunden.')
                continue
            now = fields.Datetime.now()
            spec = {
                'post_type': 'soldout',
                'planned_date': now + timedelta(hours=max(config.soldout_delay_hours or 1, 1)),
                'message': event._gl_render_post_message(config, 'soldout', sold_out=True),
            }
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
                vals = {
                    'gl_event_social_type': 'event_day_soldout',
                    'gl_requires_approval': not (config.auto_post_without_approval or event.gl_social_auto_publish_ok),
                    'gl_approved': bool(config.auto_post_without_approval or event.gl_social_auto_publish_ok),
                }
                msg = event._gl_render_post_message(config, 'event_day_soldout', sold_out=True)
                if 'message' in post._fields:
                    vals['message'] = msg
                elif 'body' in post._fields:
                    vals['body'] = msg
                post.write(vals)

    def _gl_render_post_message(self, config, post_type, sold_out=False):
        self.ensure_one()
        title = self.name or 'Veranstaltung im Groundlift Studio'
        date_text = self._gl_format_event_datetime(config.timezone)
        description = self._gl_short_description(max_chars=260)
        ticket_url = self._gl_event_ticket_url()
        hashtags = self._gl_hashtags(config)

        if post_type == 'announcement':
            headline = 'Neu angekündigt im Groundlift Studio:'
            if sold_out:
                headline = 'Neu angekündigt – bereits ausverkauft:'
            parts = [headline, title, date_text]
            if description:
                parts.append(description)
            parts.append('Infos & Tickets: %s' % ticket_url)
            parts.append(hashtags)
            return '\n\n'.join([p for p in parts if p])

        if post_type == 'reminder_3d':
            parts = [
                'In 3 Tagen bei uns:',
                title,
                date_text,
                description,
                'Jetzt Tickets sichern: %s' % ticket_url,
                hashtags,
            ]
            return '\n\n'.join([p for p in parts if p])

        if post_type == 'event_day':
            parts = [
                'Heute im Groundlift Studio:',
                title,
                date_text,
                description,
                'Tickets & Infos: %s' % ticket_url,
                hashtags,
            ]
            return '\n\n'.join([p for p in parts if p])

        if post_type == 'soldout':
            parts = [
                'Ausverkauft – danke für euer riesiges Interesse!',
                title,
                date_text,
                'Wir freuen uns auf einen besonderen Abend bei uns in der Alten Brauerei Stegen.',
                hashtags,
            ]
            return '\n\n'.join([p for p in parts if p])

        if post_type == 'event_day_soldout':
            parts = [
                'Heute vor vollem Haus:',
                title,
                date_text,
                'Danke an alle, die dabei sind. Wir freuen uns auf euch im Groundlift Studio.',
                hashtags,
            ]
            return '\n\n'.join([p for p in parts if p])

        return '\n\n'.join([title, date_text, ticket_url, hashtags])

    def _gl_short_description(self, max_chars=260):
        self.ensure_one()
        description = ''
        for field_name in ['subtitle', 'website_description', 'description', 'note']:
            if field_name in self._fields and self[field_name]:
                description = self[field_name]
                break
        if not description:
            return ''
        text = html2plaintext(description or '')
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > max_chars:
            text = text[:max_chars].rsplit(' ', 1)[0].rstrip('.,;:') + ' …'
        return text

    def _gl_event_ticket_url(self):
        self.ensure_one()
        base = self.get_base_url() if hasattr(self, 'get_base_url') else self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        path = False
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

        deduped = []
        seen = set()
        for tag in tags:
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(tag)
        return ' '.join(deduped)

    def _gl_make_hashtag(self, value):
        value = (value or '').strip().lower()
        replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'}
        for src, dst in replacements.items():
            value = value.replace(src, dst)
        value = re.sub(r'[^a-z0-9]+', '', value)
        if not value:
            return ''
        return '#' + value

    def _gl_format_event_datetime(self, tzname='Europe/Berlin'):
        self.ensure_one()
        if 'date_begin' not in self._fields or not self.date_begin:
            return ''
        tz = pytz.timezone(tzname or 'Europe/Berlin')
        date_begin = fields.Datetime.from_string(self.date_begin)
        local_start = pytz.UTC.localize(date_begin).astimezone(tz) if date_begin.tzinfo is None else date_begin.astimezone(tz)
        date_part = local_start.strftime('%d.%m.%Y')
        time_part = local_start.strftime('%H:%M')
        if 'date_end' in self._fields and self.date_end:
            date_end = fields.Datetime.from_string(self.date_end)
            local_end = pytz.UTC.localize(date_end).astimezone(tz) if date_end.tzinfo is None else date_end.astimezone(tz)
            if local_end.date() == local_start.date():
                return '%s · %s–%s Uhr' % (date_part, time_part, local_end.strftime('%H:%M'))
        return '%s · %s Uhr' % (date_part, time_part)

    def _gl_create_event_image_attachment(self):
        self.ensure_one()
        for field_name in ['x_studio_website_header', 'website_image', 'image_1920', 'image_1024', 'image_512']:
            if field_name not in self._fields:
                continue
            data = self[field_name]
            if not data:
                continue
            if isinstance(data, str):
                data = data.encode()
            try:
                # Verify base64-ish binary to avoid broken attachments.
                base64.b64decode(data, validate=False)
            except Exception:
                continue
            filename = '%s_social_header.jpg' % self._gl_filename_safe(self.name or 'event')
            existing = self.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'event.event'),
                ('res_id', '=', self.id),
                ('name', '=', filename),
            ], limit=1)
            if existing:
                return existing
            return self.env['ir.attachment'].sudo().create({
                'name': filename,
                'type': 'binary',
                'datas': data,
                'res_model': 'event.event',
                'res_id': self.id,
                'mimetype': 'image/jpeg',
            })
        return False

    def _gl_filename_safe(self, value):
        return re.sub(r'[^A-Za-z0-9_.-]+', '_', value).strip('_')[:80]

    def _gl_is_sold_out(self):
        self.ensure_one()
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
        # Ticket-level fallback: if every limited ticket is sold out.
        if 'event_ticket_ids' in self._fields and self.event_ticket_ids:
            limited_tickets = self.event_ticket_ids.filtered(lambda t: 'seats_max' in t._fields and t.seats_max)
            if limited_tickets:
                soldout_tickets = limited_tickets.filtered(
                    lambda t: ('seats_available' in t._fields and t.seats_available <= 0)
                    or ('seats_taken' in t._fields and t.seats_taken >= t.seats_max)
                )
                return len(soldout_tickets) == len(limited_tickets)
        return False

    def _gl_is_post_published(self, post):
        if 'state' not in post._fields:
            return False
        return str(post.state or '').lower() in ['posted', 'published', 'done', 'sent']

    def _gl_has_future_event_date(self):
        self.ensure_one()
        if 'date_begin' not in self._fields or not self.date_begin:
            return False
        return self.date_begin > fields.Datetime.now()

    def _gl_next_day_datetime(self, hour, minute, tzname):
        tz = pytz.timezone(tzname or 'Europe/Berlin')
        now_local = pytz.UTC.localize(fields.Datetime.now()).astimezone(tz)
        target_date = now_local.date() + timedelta(days=1)
        local_dt = datetime.combine(target_date, time(max(min(hour or 0, 23), 0), max(min(minute or 0, 59), 0)))
        return self._gl_local_naive_to_utc_naive(local_dt, tz)

    def _gl_event_relative_datetime(self, days_delta, hour, minute, tzname):
        self.ensure_one()
        if 'date_begin' not in self._fields or not self.date_begin:
            return False
        tz = pytz.timezone(tzname or 'Europe/Berlin')
        date_begin = fields.Datetime.from_string(self.date_begin)
        local_start = pytz.UTC.localize(date_begin).astimezone(tz) if date_begin.tzinfo is None else date_begin.astimezone(tz)
        target_date = local_start.date() + timedelta(days=days_delta)
        local_dt = datetime.combine(target_date, time(max(min(hour or 0, 23), 0), max(min(minute or 0, 59), 0)))
        return self._gl_local_naive_to_utc_naive(local_dt, tz)

    def _gl_local_naive_to_utc_naive(self, local_dt, tz):
        localized = tz.localize(local_dt) if local_dt.tzinfo is None else local_dt.astimezone(tz)
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    def _gl_should_create_planned_post(self, planned_dt, now, config):
        if not planned_dt:
            return False
        if config.skip_past_planned_posts and planned_dt <= now:
            return False
        return True

    def _gl_update_social_generated_flags(self):
        for event in self:
            posts = event.gl_social_post_ids
            event.gl_social_posts_generated = bool(posts)
            event.gl_soldout_social_post_created = bool(posts.filtered(lambda p: p.gl_event_social_type == 'soldout'))

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
