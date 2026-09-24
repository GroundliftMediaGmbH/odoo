"""Bridge Groundlift's legacy event text, its rich HTML, and Odoo's website HTML.

All three fields retain their existing names and types. The website side must be
updated even if the legacy Studio field cannot be discovered: previous versions
silently bypassed *all* synchronization in that case.
"""
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .conversion import html_to_plain, plain_to_html

_logger = logging.getLogger(__name__)
PARAMETER = 'gl_landingpage_text_to_html.source_field'
SKIP_SYNC = 'gl_text_to_html_skip_sync'


def _equivalent_text(first, second):
    """Only for deciding whether an existing native description is ours.

    HTML editors normalize paragraphs, NBSP and line breaks differently. Their
    readable content may still be the same. Never remove content or compare
    fuzzy substrings: unrelated existing descriptions must not be overwritten.
    """
    first_text = re.sub(r'\s+', ' ', html_to_plain(first or '')).strip()
    second_text = re.sub(r'\s+', ' ', html_to_plain(second or '')).strip()
    return first_text == second_text


class EventEvent(models.Model):
    _inherit = 'event.event'

    gl_landingpage_html = fields.Html(
        string='Landingpage Beschreibung (HTML)',
        sanitize=True,
        translate=False,
        copy=False,
        help='Formatierte Beschreibung; das bestehende Studio-Textfeld bleibt erhalten.',
    )
    gl_landingpage_native_linked = fields.Boolean(
        string='Mit Odoo-Webseitenbeschreibung verbunden', copy=False,
        help='Änderungen an HTML werden in die native Odoo-Website-Beschreibung übertragen.',
    )
    gl_landingpage_native_backup = fields.Html(
        string='Sicherung der vorherigen Odoo-Webseitenbeschreibung',
        sanitize=True, translate=False, copy=False, groups='base.group_system',
    )
    gl_landingpage_website_status = fields.Char(
        string='Website-Status', compute='_compute_gl_landingpage_website_status',
    )

    @api.depends('gl_landingpage_html', 'description', 'gl_landingpage_native_linked')
    def _compute_gl_landingpage_website_status(self):
        for event in self:
            if not event.gl_landingpage_html:
                event.gl_landingpage_website_status = _('HTML-Beschreibung ist noch leer.')
            elif event.gl_landingpage_html == (event.description or ''):
                event.gl_landingpage_website_status = _('HTML und native Odoo-Webseitenbeschreibung sind identisch.')
            elif event.gl_landingpage_native_linked:
                event.gl_landingpage_website_status = _(
                    'Verknüpft, aber HTML und native Webseitenbeschreibung unterscheiden sich. '
                    'Bitte „HTML jetzt auf Odoo-Webseite übernehmen“ ausführen.'
                )
            else:
                event.gl_landingpage_website_status = _(
                    'Die native Odoo-Webseitenbeschreibung ist noch nicht verbunden. '
                    'Bitte den Button „HTML jetzt auf Odoo-Webseite übernehmen“ verwenden.'
                )

    @api.model
    def _gl_get_plain_field_name(self):
        configured = self.env['ir.config_parameter'].sudo().get_param(PARAMETER, '').strip()
        if configured:
            field = self._fields.get(configured)
            if field and field.type == 'text' and configured != 'description':
                return configured
            _logger.warning('Landingpage Text_to_HTML: invalid Studio source field %r.', configured)
            return None
        hits = [
            name for name, field in self._fields.items()
            if field.type == 'text'
            and field.string.strip().casefold() in ('event beschreibung', 'eventbeschreibung')
        ]
        if len(hits) == 1:
            return hits[0]
        _logger.warning(
            'Landingpage Text_to_HTML: ambiguous Studio source field; set %s (matches: %s).',
            PARAMETER, hits,
        )
        return None

    def _gl_internal_write(self, vals):
        """Bypass our own bridge, not third-party model.write overrides."""
        return self.with_context(**{SKIP_SYNC: True}).write(vals)

    def _gl_fill_html_from_plain(self):
        source = self._gl_get_plain_field_name()
        for event in self:
            if source and not event.gl_landingpage_html and event[source]:
                event._gl_internal_write({'gl_landingpage_html': plain_to_html(event[source])})

    def _gl_link_native_if_safe(self):
        """Link only empty/semantically identical native descriptions; never erase others."""
        for event in self:
            html = event.gl_landingpage_html
            if not html:
                continue
            native = event.description or ''
            if (event.gl_landingpage_native_linked or not native
                    or _equivalent_text(native, html)):
                changes = {'gl_landingpage_native_linked': True}
                if native != html:
                    changes['description'] = html
                event._gl_internal_write(changes)
            else:
                _logger.info(
                    'Landingpage Text_to_HTML: native website description of event %s '
                    'differs; explicit per-event confirmation needed.', event.id,
                )

    def action_gl_copy_plain_to_html(self):
        if not self._gl_get_plain_field_name():
            raise UserError(_(
                'Quellfeld nicht erkannt. Systemparameter '
                'gl_landingpage_text_to_html.source_field auf den technischen '
                'Namen des bestehenden event.event-Textfelds setzen.'
            ))
        self._gl_fill_html_from_plain()
        self._gl_link_native_if_safe()
        return True

    def action_gl_sync_native_if_safe(self):
        self._gl_fill_html_from_plain()
        self._gl_link_native_if_safe()
        return True

    def action_gl_force_native_link(self):
        """Explicit one-click repair on affected events; backup native HTML once."""
        for event in self:
            if not event.gl_landingpage_html:
                event._gl_fill_html_from_plain()
            if not event.gl_landingpage_html:
                raise UserError(_('Bitte zuerst eine Landingpage-HTML-Beschreibung eintragen.'))
            updates = {
                'description': event.gl_landingpage_html,
                'gl_landingpage_native_linked': True,
            }
            if (not event.gl_landingpage_native_backup and event.description
                    and event.description != event.gl_landingpage_html):
                updates['gl_landingpage_native_backup'] = event.description
            event._gl_internal_write(updates)
        return True

    @api.model
    def _gl_migrate_existing(self):
        """Safe on module update: no reset of existing custom formatting."""
        events = self.sudo()
        last_id = 0
        while True:
            batch = events.search([('id', '>', last_id)], order='id', limit=200)
            if not batch:
                break
            batch._gl_fill_html_from_plain()
            batch._gl_link_native_if_safe()
            last_id = batch[-1].id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get(SKIP_SYNC):
            return records
        source = self._gl_get_plain_field_name()
        for event, vals in zip(records, vals_list):
            if 'gl_landingpage_html' in vals:
                if source:
                    event._gl_internal_write({source: html_to_plain(event.gl_landingpage_html)})
            elif source and event[source] and not event.gl_landingpage_html:
                event._gl_fill_html_from_plain()
            # Keep a separately supplied native description until user confirms
            # if its readable content differs from rich HTML.
            event._gl_link_native_if_safe()
        return records

    def write(self, vals):
        if self.env.context.get(SKIP_SYNC):
            return super().write(vals)

        source = self._gl_get_plain_field_name()
        editing_html = 'gl_landingpage_html' in vals
        editing_plain = bool(source and source in vals)
        editing_native = 'description' in vals
        if not (editing_html or editing_plain or editing_native):
            return super().write(vals)

        before = {
            event.id: (
                event.gl_landingpage_html or '',
                event.description or '',
                event[source] if source else '',
                event.gl_landingpage_native_linked,
            )
            for event in self
        }
        vals = dict(vals)
        if editing_plain and not editing_html:
            vals['gl_landingpage_html'] = plain_to_html(vals[source])
        result = super().write(vals)

        for event in self:
            old_html, old_native, old_plain, previously_linked = before[event.id]
            if editing_html or editing_plain:
                current_html = event.gl_landingpage_html or ''
                updates = {}
                if source and editing_html:
                    plain = html_to_plain(current_html)
                    if event[source] != plain:
                        updates[source] = plain
                # CRITICAL: previous v1.1 aborted this step if the optional
                # Studio field was not uniquely discovered. Rich HTML MUST
                # reach native event.description independently of source.
                # Compare with the OLD content, so bold-only edits link too.
                safe_to_link = (
                    previously_linked or not old_native
                    or _equivalent_text(old_native, old_html)
                    or (old_plain and _equivalent_text(old_native, old_plain))
                    or _equivalent_text(old_native, current_html)
                )
                if safe_to_link:
                    updates['gl_landingpage_native_linked'] = True
                    if event.description != current_html:
                        updates['description'] = current_html
                if updates:
                    event._gl_internal_write(updates)
            elif editing_native and event.gl_landingpage_native_linked:
                # Native website editor writes description directly. Bring
                # that sanitized HTML back to the Groundlift rich field.
                native = event.description or ''
                updates = {}
                if event.gl_landingpage_html != native:
                    updates['gl_landingpage_html'] = native
                if source:
                    text = html_to_plain(native)
                    if event[source] != text:
                        updates[source] = text
                if updates:
                    event._gl_internal_write(updates)
        return result
