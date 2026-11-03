# -*- coding: utf-8 -*-
"""Keep event social images in sync with the *rendered* Graphics-app outputs.

The event-header image stays attached as the original fallback; do not replace
it at source or modify Graphics-app originals.  All generated attachments are
immutable snapshots so editing an output cannot change an already sent post.
"""

import base64
import hashlib
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SocialPostGraphics(models.Model):
    _inherit = 'social.post'

    gl_graphics_fallback_captured = fields.Boolean(copy=False, default=False)
    gl_graphics_fallback_image_ids = fields.Many2many(
        'ir.attachment', 'gl_social_post_graphics_fallback_rel',
        'post_id', 'attachment_id', string='Ursprüngliche Social-Bilder (Fallback)',
        copy=False,
    )
    gl_graphics_output_id = fields.Many2one(
        'gl.graphics.output', string='Verwendete Grafik-App-Ausgabe',
        ondelete='set null', copy=False, index=True,
    )
    gl_graphics_output_write_date = fields.Datetime(copy=False)
    gl_graphics_source_hash = fields.Char(copy=False)
    gl_graphics_attachment_id = fields.Many2one(
        'ir.attachment', string='Automatisch eingesetztes Social-Bild',
        ondelete='set null', copy=False,
    )
    gl_graphics_final_checked_for = fields.Datetime(
        string='Grafik 24 Stunden vor diesem Posting erneut geprüft', copy=False,
    )

    def _gl_graphics_is_unpublished(self):
        self.ensure_one()
        if not self.gl_auto_generated or not self.gl_event_id:
            return False
        if 'state' in self._fields and (self.state or '').lower() in (
            'posted', 'published', 'done', 'sent',
        ):
            return False
        if 'published_date' in self._fields and self.published_date:
            return False
        return True

    def _gl_graphics_find_output(self):
        """Use the newest *rendered* output of the matching event and format."""
        self.ensure_one()
        key = 'social_post' if (self.gl_publication_kind or 'story') == 'feed' else 'social_story'
        domain = [
            ('poster_id.event_id', '=', self.gl_event_id.id),
            ('poster_id.active', '=', True),
            ('template_key', '=', key),
        ]
        if 'company_id' in self.gl_event_id._fields and self.gl_event_id.company_id:
            domain.append(('poster_id.company_id', '=', self.gl_event_id.company_id.id))
        return self.env['gl.graphics.output'].sudo().search(
            domain, order='write_date desc, id desc', limit=1,
        )

    def _gl_graphics_snapshot_attachment(self, output, source_hash, decoded):
        """Share immutable image snapshots for equivalent posts, not mutable outputs."""
        self.ensure_one()
        event = self.gl_event_id.sudo()
        soldout = self.gl_event_social_type in ('soldout', 'event_day_soldout')
        kind = self.gl_publication_kind or 'story'
        badge_token = ''
        if soldout:
            config = self.env['gl.event.social.config'].get_config()
            badge_token = event._gl_soldout_badge_cache_token(config)
        if soldout:
            try:
                prepared = event._gl_prepare_image_for_soldout_badge(decoded, publication_kind=kind)
                decoded = event._gl_add_soldout_badge_to_image(
                    prepared, publication_kind=kind, config=config,
                )
            except Exception:
                _logger.exception('Could not add sold-out badge for event %s; retaining current social image.', event.id)
                return False
        if decoded.startswith(b'\xff\xd8\xff'):
            extension, mimetype = 'jpg', 'image/jpeg'
        elif decoded.startswith(b'\x89PNG\r\n\x1a\n'):
            extension, mimetype = 'png', 'image/png'
        else:
            _logger.warning('Graphics output %s is not a JPEG/PNG image.', output.id)
            return False
        name = 'gl_graphics_event_%s_%s_%s_%s.%s' % (
            event.id, kind, output.id, source_hash[:32], extension,
        )
        attachments = self.env['ir.attachment'].sudo()
        existing = attachments.search([
            ('res_model', '=', 'event.event'),
            ('res_id', '=', event.id),
            ('name', '=', name),
        ], limit=1)
        return existing or attachments.create({
            'name': name,
            'type': 'binary',
            'datas': base64.b64encode(decoded),
            'res_model': 'event.event',
            'res_id': event.id,
            'mimetype': mimetype,
        })

    def _gl_sync_graphics_one(self, now=None, force=False):
        """Refresh an unpublished post, without changing date, content or approval."""
        self.ensure_one()
        if not self._gl_graphics_is_unpublished():
            return False
        image_field = self._gl_attachment_field_name()
        if not image_field:
            return False
        now = now or fields.Datetime.now()
        planned = self._gl_planned_datetime()
        final_due = bool(
            planned and now >= planned - timedelta(days=1)
            and self.gl_graphics_final_checked_for != planned
        )
        vals = {}
        if final_due:
            vals['gl_graphics_final_checked_for'] = planned

        output = self._gl_graphics_find_output()
        if not output:
            if self.gl_graphics_output_id or self.gl_graphics_attachment_id:
                if self.gl_graphics_fallback_captured:
                    vals[image_field] = [(6, 0, self.gl_graphics_fallback_image_ids.ids)]
                vals.update({
                    'gl_graphics_output_id': False,
                    'gl_graphics_output_write_date': False,
                    'gl_graphics_source_hash': False,
                    'gl_graphics_attachment_id': False,
                })
        else:
            attached = self.gl_graphics_attachment_id and self.gl_graphics_attachment_id in self._gl_image_attachments()
            stamp = output.write_date
            changed = (
                output != self.gl_graphics_output_id
                or stamp != self.gl_graphics_output_write_date
                or not attached
                or final_due
                or force
            )
            if changed:
                encoded = output.image
                try:
                    decoded = base64.b64decode(encoded) if encoded else b''
                except (ValueError, TypeError):
                    decoded = b''
                if not decoded:
                    _logger.warning('Graphics output %s has no readable image; keeping previous image.', output.id)
                    return False
                soldout = self.gl_event_social_type in ('soldout', 'event_day_soldout')
                badge_token = ''
                if soldout:
                    badge_token = self.gl_event_id._gl_soldout_badge_cache_token(
                        self.env['gl.event.social.config'].get_config(),
                    )
                source_hash = hashlib.sha256(decoded + str(badge_token).encode('utf-8')).hexdigest()
                if (
                    source_hash != self.gl_graphics_source_hash
                    or output != self.gl_graphics_output_id
                    or not attached
                ):
                    attachment = self._gl_graphics_snapshot_attachment(output, source_hash, decoded)
                    if not attachment:
                        return False
                    if not self.gl_graphics_fallback_captured:
                        vals.update({
                            'gl_graphics_fallback_captured': True,
                            'gl_graphics_fallback_image_ids': [(6, 0, self._gl_image_attachments().ids)],
                        })
                    vals[image_field] = [(6, 0, [attachment.id])]
                    vals['gl_graphics_attachment_id'] = attachment.id
                vals.update({
                    'gl_graphics_output_id': output.id,
                    'gl_graphics_output_write_date': stamp,
                    'gl_graphics_source_hash': source_hash,
                })
        if vals:
            # Avoid the existing default-crop/approval hooks: Graphics supplies a
            # finished canvas. Approved/scheduled posts must stay approved/scheduled.
            self.sudo().with_context(
                gl_skip_groundlift_approval_hook=True,
                gl_skip_auto_image_adjustment=True,
                gl_skip_image_aspect_update=True,
            ).write(vals)
            if image_field in vals:
                self._gl_update_image_aspect_status()
        return bool(vals)

    def _gl_sync_graphics_for_posts(self, force=False):
        for post in self:
            try:
                # Savepoints keep a bad output from blocking unrelated posts.
                with self.env.cr.savepoint():
                    post._gl_sync_graphics_one(force=force)
            except Exception:
                _logger.exception('Graphics sync failed for social.post %s.', post.id)
        return True

    @api.model
    def _cron_gl_sync_social_graphics(self):
        """Every 15 minutes, including a forced refresh at the 24-hour mark."""
        now = fields.Datetime.now()
        domain = [
            ('gl_auto_generated', '=', True),
            ('gl_event_id', '!=', False),
            ('gl_planned_date', '>=', now - timedelta(hours=2)),
        ]
        # Paging avoids starving posts beyond the first page if the backlog grows.
        offset, batch_size = 0, 150
        while True:
            posts = self.sudo().search(
                domain, order='gl_planned_date asc, id asc',
                offset=offset, limit=batch_size,
            )
            if not posts:
                break
            posts._gl_sync_graphics_for_posts()
            offset += len(posts)
        return True

    def _gl_intercept_native_publish_action(self, method_name):
        # Last possible check for native Odoo actions, in addition to cron/save.
        self._gl_sync_graphics_for_posts(force=True)
        return super()._gl_intercept_native_publish_action(method_name)
