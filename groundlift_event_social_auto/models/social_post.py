# -*- coding: utf-8 -*-

import base64
import logging
import re
from io import BytesIO
from datetime import timedelta

try:
    from PIL import Image
except Exception:
    Image = None

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
    gl_publication_kind = fields.Selection([
        ('story', 'Story'),
        ('feed', 'Feed-Post'),
    ], string='Ziel-Format', default='story', copy=False, index=True)
    gl_publish_as_feed_post = fields.Boolean(
        string='Als Feed-Post statt Story veröffentlichen',
        default=False,
        copy=False,
        help='Aus: Story. An: normaler Feed-Post. Standard ist Story.',
    )
    gl_image_aspect_status = fields.Selection([
        ('missing', 'Kein Bild'),
        ('ok', 'Format passt'),
        ('warning', 'Format prüfen'),
    ], string='Bildformat-Status', default='missing', copy=False, readonly=True)
    gl_image_aspect_message = fields.Text(string='Bildformat-Hinweis', copy=False, readonly=True)
    gl_adjust_image_crop = fields.Boolean(string='Ausschnitt anpassen', default=True, copy=False)

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

    def action_gl_open_regenerate_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Diesen Post neu generieren',
            'res_model': 'gl.social.post.regenerate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_post_id': self.id},
        }

    def action_gl_open_replace_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Post ersetzen mit',
            'res_model': 'gl.social.post.replace.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_post_id': self.id},
        }

    def action_gl_open_image_adjust_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bildformat anpassen',
            'res_model': 'gl.social.post.image.adjust.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_post_id': self.id},
        }

    def action_gl_apply_selected_image_adjustment(self):
        self.ensure_one()
        if self.gl_adjust_image_crop:
            return self.action_gl_open_image_adjust_wizard()
        raise UserError('Bitte zuerst „Ausschnitt anpassen“ aktivieren.')

    def action_gl_check_image_aspect(self):
        self._gl_update_image_aspect_status()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Bildformat geprüft',
                'message': '\n'.join([p.gl_image_aspect_message or 'Kein Hinweis' for p in self]),
                'sticky': False,
                'type': 'success' if all(p.gl_image_aspect_status == 'ok' for p in self) else 'warning',
            },
        }

    def _gl_message_field_name(self):
        for field_name in ('message', 'message_deserialized', 'body'):
            if field_name in self._fields:
                return field_name
        return False

    def _gl_current_message(self):
        self.ensure_one()
        field_name = self._gl_message_field_name()
        return self[field_name] if field_name and self[field_name] else ''

    def _gl_message_write_vals(self, message):
        field_name = self._gl_message_field_name()
        return {field_name: message or ''} if field_name else {}

    def _gl_regenerate_ai_text(self, mode='variant', extra_information=''):
        self.ensure_one()
        config = self.env['gl.event.social.config'].get_config()
        post_type = self.gl_event_social_type or 'announcement'
        event = self.gl_event_id
        sold_out = bool(event and event._gl_is_sold_out())
        current_message = self._gl_current_message()
        generated = ''
        if event:
            generated = config._gl_openai_regenerate_post_text(
                post=self,
                event=event,
                mode=mode,
                extra_information=extra_information,
                sold_out=sold_out,
            )
            if not generated:
                generated = event._gl_render_post_message(
                    config,
                    post_type,
                    sold_out=sold_out,
                    extra_instruction=extra_information if mode == 'add_info' else '',
                )
            if sold_out:
                attachment = event._gl_create_event_image_attachment(sold_out=True, publication_kind=self.gl_publication_kind or 'story')
                if attachment:
                    self._gl_replace_image_attachments(attachment)
        else:
            generated = config._gl_openai_regenerate_generic_text(current_message, mode=mode, extra_information=extra_information) or current_message

        vals = self._gl_message_write_vals(generated)
        vals.update({
            'gl_requires_approval': True,
            'gl_approved': False,
        })
        if 'scheduled_date' in self._fields and self.gl_planned_date:
            vals['scheduled_date'] = self.gl_planned_date
        self.with_context(gl_skip_groundlift_approval_hook=True).write(vals)
        self._gl_force_draft_if_possible()
        self._gl_update_image_aspect_status()
        return True

    def _gl_replace_with_event(self, event, post_type='announcement', extra_information=''):
        self.ensure_one()
        event.ensure_one()
        config = self.env['gl.event.social.config'].get_config()
        sold_out = event._gl_is_sold_out()
        message = event._gl_render_post_message(
            config,
            post_type or 'announcement',
            sold_out=sold_out,
            extra_instruction=extra_information or '',
        )
        vals = {
            'gl_event_id': event.id,
            'gl_event_social_type': post_type or 'announcement',
            'gl_auto_generated': True,
            'gl_requires_approval': True,
            'gl_approved': False,
        }
        vals.update(self._gl_message_write_vals(message))
        attachment = event._gl_create_event_image_attachment(sold_out=sold_out, publication_kind=self.gl_publication_kind or 'story')
        if attachment:
            image_field = self._gl_attachment_field_name()
            if image_field:
                vals[image_field] = [(6, 0, [attachment.id])]
        self.with_context(gl_skip_groundlift_approval_hook=True).write(vals)
        self._gl_force_draft_if_possible()
        self._gl_update_image_aspect_status()
        return True

    def _gl_replace_with_gap_filler(self, extra_information=''):
        self.ensure_one()
        config = self.env['gl.event.social.config'].get_config()
        candidate, homepage_context = config._gl_choose_homepage_image_candidate()
        image_context = config._gl_clean_homepage_context(candidate.get('context') if candidate else '', max_chars=900)
        homepage_context = config._gl_clean_homepage_context(homepage_context, max_chars=1400)
        generated = config._gl_openai_generate_gap_filler(image_context + ('\n' + extra_information if extra_information else ''), homepage_context) if config.openai_api_key else {}
        text = config._gl_clean_homepage_context((generated.get('text') if isinstance(generated, dict) else '') or '', max_chars=700)
        if not text:
            text = config._gl_fallback_gap_filler_text(image_context)
        hashtags = config._gl_normalize_hashtags(generated.get('hashtags') if isinstance(generated, dict) else []) or (config.default_hashtags or '#groundlift #ammersee')
        message = '%s\n\n%s' % (text.strip(), hashtags.strip())
        vals = {
            'gl_event_id': False,
            'gl_event_social_type': 'gap_filler',
            'gl_auto_generated': True,
            'gl_requires_approval': True,
            'gl_approved': False,
        }
        vals.update(self._gl_message_write_vals(message))
        attachment = config._gl_download_homepage_image_attachment(candidate['url']) if candidate and candidate.get('url') else False
        if attachment:
            if candidate and candidate.get('url'):
                config.sudo().write({'last_homepage_image_url': candidate['url']})
            image_field = self._gl_attachment_field_name()
            if image_field:
                vals[image_field] = [(6, 0, [attachment.id])]
        self.with_context(gl_skip_groundlift_approval_hook=True).write(vals)
        self._gl_force_draft_if_possible()
        self._gl_update_image_aspect_status()
        return True

    def _gl_attachment_field_name(self):
        for image_field in ('image_ids', 'attachment_ids'):
            field = self._fields.get(image_field)
            if field and getattr(field, 'type', '') in ('many2many', 'one2many') and getattr(field, 'comodel_name', '') == 'ir.attachment':
                return image_field
        return False

    def _gl_image_attachments(self):
        self.ensure_one()
        image_field = self._gl_attachment_field_name()
        if not image_field:
            return self.env['ir.attachment']
        return self[image_field].filtered(lambda a: (a.mimetype or '').startswith('image/') or (a.name or '').lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))

    def _gl_replace_image_attachments(self, attachment):
        self.ensure_one()
        image_field = self._gl_attachment_field_name()
        if image_field and attachment:
            self.with_context(gl_skip_groundlift_approval_hook=True).write({image_field: [(6, 0, [attachment.id])]})

    def _gl_replace_multiple_image_attachments(self, attachments):
        self.ensure_one()
        image_field = self._gl_attachment_field_name()
        if image_field and attachments:
            self.with_context(gl_skip_groundlift_approval_hook=True, gl_skip_auto_image_adjustment=True).write({image_field: [(6, 0, attachments.ids)]})

    def _gl_needs_image_adjustment(self, attachment):
        self.ensure_one()
        dims = self._gl_attachment_dimensions(attachment)
        if not dims:
            return False
        width, height = dims
        ratio = float(width) / float(height or 1)
        return not self._gl_ratio_is_acceptable(ratio)

    def _gl_auto_apply_default_image_adjustment(self):
        for post in self:
            if post.env.context.get('gl_skip_auto_image_adjustment'):
                continue
            attachments = post._gl_image_attachments()
            if not attachments:
                continue
            if not post.gl_adjust_image_crop:
                continue
            needs_adjustment = any(post._gl_needs_image_adjustment(attachment) for attachment in attachments)
            if not needs_adjustment:
                continue
            adjusted = post.env['ir.attachment']
            for attachment in attachments:
                adjusted |= post._gl_crop_attachment_to_target(attachment)
            if adjusted:
                vals = {
                    'gl_requires_approval': True,
                    'gl_approved': False,
                    'gl_adjust_image_crop': True,
                }
                image_field = post._gl_attachment_field_name()
                if image_field:
                    vals[image_field] = [(6, 0, adjusted.ids)]
                post.with_context(gl_skip_groundlift_approval_hook=True, gl_skip_auto_image_adjustment=True).write(vals)
                post._gl_force_draft_if_possible()

    @api.model
    def _gl_pil_cover_crop(self, image, target_ratio, focal_x='center', focal_y='center'):
        """Crop a PIL image to target_ratio while preserving maximum pixels."""
        if not image or not target_ratio:
            return image
        width, height = image.size
        current_ratio = float(width) / float(height or 1)
        if abs(current_ratio - target_ratio) <= 0.001:
            return image
        if current_ratio > target_ratio:
            new_width = int(height * target_ratio)
            if focal_x == 'left':
                left = 0
            elif focal_x == 'right':
                left = width - new_width
            else:
                left = int((width - new_width) / 2)
            box = (max(left, 0), 0, min(left + new_width, width), height)
        else:
            new_height = int(width / target_ratio)
            if focal_y == 'top':
                top = 0
            elif focal_y == 'bottom':
                top = height - new_height
            else:
                top = int((height - new_height) / 2)
            box = (0, max(top, 0), width, min(top + new_height, height))
        return image.crop(box)

    def _gl_crop_attachment_to_target(self, attachment, focal_x='center', focal_y='center'):
        self.ensure_one()
        if not Image:
            raise UserError('Pillow/PIL ist auf dem Odoo-Server nicht verfügbar. Zuschneiden ist deshalb nicht möglich.')
        if not attachment or not attachment.datas:
            raise UserError('Kein Bild zum Zuschneiden gefunden.')
        target_ratio = self._gl_target_aspect_ratio()
        image_bytes = base64.b64decode(attachment.datas)
        with Image.open(BytesIO(image_bytes)) as image:
            image = image.convert('RGB')
            image = self._gl_pil_cover_crop(image, target_ratio, focal_x=focal_x, focal_y=focal_y)
            output = BytesIO()
            image.save(output, format='JPEG', quality=95)
        name = 'crop_%s' % (attachment.name or 'social_image.jpg')
        return self.env['ir.attachment'].sudo().create({
            'name': re.sub(r'[^A-Za-z0-9_.-]+', '_', name)[:110],
            'type': 'binary',
            'datas': base64.b64encode(output.getvalue()),
            'res_model': attachment.res_model or 'social.post',
            'res_id': attachment.res_id or self.id,
            'mimetype': 'image/jpeg',
        })

    def _gl_attachment_dimensions(self, attachment):
        if not Image or not attachment or not attachment.datas:
            return False
        try:
            image_bytes = base64.b64decode(attachment.datas)
            with Image.open(BytesIO(image_bytes)) as image:
                return image.size
        except Exception:
            return False

    def _gl_target_aspect_ratio(self):
        self.ensure_one()
        if (self.gl_publication_kind or 'story') == 'story':
            return 9.0 / 16.0
        # Für kombinierte Instagram/Facebook-Feedposts ist 4:5 die sicherste
        # vertikale Feed-Fläche. Facebook akzeptiert breiter, Instagram ist enger.
        if self.gl_has_instagram_target:
            return 4.0 / 5.0
        return 1.0

    def _gl_target_aspect_label(self):
        self.ensure_one()
        if (self.gl_publication_kind or 'story') == 'story':
            return 'Story 9:16'
        if self.gl_has_instagram_target:
            return 'Feed 4:5 / 1:1-kompatibel'
        return 'Feed 1:1-kompatibel'

    def _gl_ratio_is_acceptable(self, ratio):
        self.ensure_one()
        if not ratio:
            return False
        if (self.gl_publication_kind or 'story') == 'story':
            return abs(ratio - (9.0 / 16.0)) <= 0.035
        if self.gl_has_instagram_target:
            return 0.79 <= ratio <= 1.92
        if self.gl_has_facebook_target:
            return 0.70 <= ratio <= 1.92
        return 0.79 <= ratio <= 1.92

    def _gl_update_image_aspect_status(self):
        for post in self:
            if self.env.context.get('gl_skip_image_aspect_update'):
                continue
            vals = {}
            attachments = post._gl_image_attachments()
            if not attachments:
                vals = {
                    'gl_image_aspect_status': 'missing',
                    'gl_image_aspect_message': 'Kein Bild gefunden. Für Storys wird 9:16 empfohlen; für Feedposts 4:5 bis 1.91:1.',
                }
            else:
                messages, ok_all = [], True
                target_label = post._gl_target_aspect_label()
                for attachment in attachments:
                    dims = post._gl_attachment_dimensions(attachment)
                    if not dims:
                        ok_all = False
                        messages.append('%s: Bildgröße konnte nicht gelesen werden.' % (attachment.name or 'Bild'))
                        continue
                    width, height = dims
                    ratio = float(width) / float(height or 1)
                    ok = post._gl_ratio_is_acceptable(ratio)
                    ok_all = ok_all and ok
                    messages.append('%s: %sx%s (%.3f) → Ziel %s%s' % (
                        attachment.name or 'Bild',
                        width,
                        height,
                        ratio,
                        target_label,
                        ' ✓' if ok else ' ⚠ bitte anpassen',
                    ))
                vals = {
                    'gl_image_aspect_status': 'ok' if ok_all else 'warning',
                    'gl_image_aspect_message': '\n'.join(messages),
                }
            post.with_context(gl_skip_groundlift_approval_hook=True, gl_skip_image_aspect_update=True).write(vals)
        return True

    def _gl_sync_publication_kind_vals(self, vals):
        vals = dict(vals or {})
        if 'gl_publish_as_feed_post' in vals and 'gl_publication_kind' not in vals:
            vals['gl_publication_kind'] = 'feed' if vals.get('gl_publish_as_feed_post') else 'story'
        elif 'gl_publication_kind' in vals and 'gl_publish_as_feed_post' not in vals:
            vals['gl_publish_as_feed_post'] = vals.get('gl_publication_kind') == 'feed'
        elif 'gl_publication_kind' not in vals and 'gl_publish_as_feed_post' not in vals and vals.get('gl_auto_generated'):
            vals['gl_publication_kind'] = vals.get('gl_publication_kind') or 'story'
            vals['gl_publish_as_feed_post'] = False
        publication_kind = vals.get('gl_publication_kind')
        if publication_kind:
            vals.update(self._gl_native_publication_kind_vals(publication_kind))
        return vals

    def _gl_native_publication_kind_vals(self, publication_kind):
        """Best-effort bridge for Odoo builds that expose a native story/feed selector.

        Odoo Social field names changed across releases and editions. The module
        keeps Groundlift's own selector authoritative and mirrors it only into
        native fields that actually exist and visibly support story/feed values.
        """
        result = {}
        preferred_story = ('story', 'stories', 'instagram_story', 'ig_story')
        preferred_feed = ('post', 'feed', 'feed_post', 'instagram_post', 'facebook_post')
        preferred = preferred_story if publication_kind == 'story' else preferred_feed
        for field_name, field in self._fields.items():
            if field_name.startswith('gl_') or field_name in ('post_method', 'state'):
                continue
            lname = field_name.lower()
            if not any(token in lname for token in ('story', 'stories', 'format', 'kind', 'publication', 'content', 'placement', 'post_type')):
                continue
            if getattr(field, 'type', '') == 'selection' and isinstance(getattr(field, 'selection', None), (list, tuple)):
                keys = [item[0] for item in field.selection]
                labels = {item[0]: str(item[1]).lower() for item in field.selection}
                for key in preferred:
                    if key in keys:
                        result[field_name] = key
                        break
                if field_name not in result:
                    for key in keys:
                        label = labels.get(key, '')
                        if publication_kind == 'story' and 'story' in label:
                            result[field_name] = key
                            break
                        if publication_kind == 'feed' and any(word in label for word in ('feed', 'post', 'beitrag')):
                            result[field_name] = key
                            break
            elif getattr(field, 'type', '') == 'boolean' and 'story' in lname:
                result[field_name] = publication_kind == 'story'
        return result

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
        prepared_vals_list = []
        for vals in vals_list:
            vals = self._gl_sync_publication_kind_vals(vals)
            if media_field and getattr(media_field, 'comodel_name', '') == 'social.media' and account_field_name:
                if vals.get('gl_auto_generated') and account_field_name in vals and 'media_ids' not in vals:
                    commands = self._gl_media_commands_from_account_commands(vals.get(account_field_name))
                    if commands is not False:
                        vals['media_ids'] = commands
            prepared_vals_list.append(vals)
        posts = super().create(prepared_vals_list)
        posts._gl_auto_apply_default_image_adjustment()
        posts._gl_update_image_aspect_status()
        return posts

    def write(self, vals):
        original_vals = dict(vals or {})
        vals = self._gl_sync_publication_kind_vals(vals)
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
        image_relevant_fields = {'image_ids', 'attachment_ids', 'gl_publication_kind', 'gl_publish_as_feed_post', 'account_ids', 'social_account_ids', 'gl_adjust_image_crop'}
        if image_relevant_fields.intersection(original_vals.keys()) and not self.env.context.get('gl_skip_image_aspect_update'):
            self._gl_auto_apply_default_image_adjustment()
            self._gl_update_image_aspect_status()
        return result

    def unlink(self):
        events = self.mapped('gl_event_id')
        result = super().unlink()
        if events:
            events._gl_update_social_generated_flags()
        return result
