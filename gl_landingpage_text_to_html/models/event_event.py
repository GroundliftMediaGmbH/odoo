"""Groundlift landing-page HTML bridge for Odoo 19.

`gl_landingpage_html` is the authoritative rich-text source whenever it contains
content.  The native `event.event.description` is kept byte-for-byte in sync so
all standard Odoo website templates (including `/event/.../register`) render the
same formatting.  A pre-existing differing native description is backed up once
before it is replaced.
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
    """Compare readable content while ignoring harmless HTML differences."""
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
        help=(
            'Formatierte Beschreibung. Sobald dieses Feld Inhalt enthält, ist es '
            'die führende Quelle für die Odoo-Veranstaltungsseite.'
        ),
    )
    gl_landingpage_native_linked = fields.Boolean(
        string='Mit Odoo-Webseitenbeschreibung verbunden', copy=False,
        help='HTML und native Odoo-Webseitenbeschreibung werden automatisch synchron gehalten.',
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
            html = event.gl_landingpage_html or ''
            native = event.description or ''
            if not html:
                event.gl_landingpage_website_status = _('HTML-Beschreibung ist noch leer.')
            elif html == native:
                event.gl_landingpage_website_status = _(
                    'HTML und native Odoo-Webseitenbeschreibung sind identisch.'
                )
            else:
                event.gl_landingpage_website_status = _(
                    'HTML und Website weichen ab. Beim Speichern des HTML-Feldes wird die '
                    'Website automatisch auf diesen Stand synchronisiert.'
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
            and (field.string or '').strip().casefold() in ('event beschreibung', 'eventbeschreibung')
        ]
        if len(hits) == 1:
            return hits[0]
        _logger.warning(
            'Landingpage Text_to_HTML: ambiguous Studio source field; set %s (matches: %s).',
            PARAMETER, hits,
        )
        return None

    def _gl_internal_write(self, vals):
        """Bypass only this module's bridge, preserving all other write overrides."""
        return self.with_context(**{SKIP_SYNC: True}).write(vals)

    def _gl_fill_html_from_plain(self):
        source = self._gl_get_plain_field_name()
        for event in self:
            if source and not event.gl_landingpage_html and event[source]:
                event._gl_internal_write({'gl_landingpage_html': plain_to_html(event[source])})

    def _gl_sync_html_to_native(self, backup=True):
        """Make rich HTML authoritative and mirror it to Odoo's native HTML field.

        This is intentionally exact instead of a semantic text comparison: formatting
        such as <strong>, links, lists and headings is precisely what must reach the
        public event page.
        """
        for event in self:
            html = event.gl_landingpage_html or ''
            if not html:
                continue

            updates = {'gl_landingpage_native_linked': True}
            native = event.description or ''
            if native != html:
                if backup and native and not event.gl_landingpage_native_backup:
                    updates['gl_landingpage_native_backup'] = native
                updates['description'] = html
            if updates.get('description') is not None or not event.gl_landingpage_native_linked:
                event._gl_internal_write(updates)

    def _gl_link_native_if_safe(self):
        """Backward-compatible method name; v1.3 makes the HTML field authoritative."""
        self._gl_sync_html_to_native(backup=True)

    def action_gl_copy_plain_to_html(self):
        if not self._gl_get_plain_field_name():
            raise UserError(_(
                'Quellfeld nicht erkannt. Systemparameter '
                'gl_landingpage_text_to_html.source_field auf den technischen '
                'Namen des bestehenden event.event-Textfelds setzen.'
            ))
        self._gl_fill_html_from_plain()
        self._gl_sync_html_to_native(backup=True)
        return True

    def action_gl_sync_native_if_safe(self):
        self._gl_fill_html_from_plain()
        self._gl_sync_html_to_native(backup=True)
        return True

    def action_gl_force_native_link(self):
        for event in self:
            if not event.gl_landingpage_html:
                event._gl_fill_html_from_plain()
            if not event.gl_landingpage_html:
                raise UserError(_('Bitte zuerst eine Landingpage-HTML-Beschreibung eintragen.'))
        self._gl_sync_html_to_native(backup=True)
        return True

    @api.model
    def _gl_migrate_existing(self):
        """Backfill and synchronize existing events in bounded batches.

        Called both on first install and by the versioned upgrade migration so an
        ordinary Apps -> Upgrade also repairs events that already had HTML in v1.2.
        """
        events = self.sudo()
        last_id = 0
        while True:
            batch = events.search([('id', '>', last_id)], order='id', limit=200)
            if not batch:
                break
            batch._gl_fill_html_from_plain()
            batch._gl_sync_html_to_native(backup=True)
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
            if event.gl_landingpage_html:
                event._gl_sync_html_to_native(backup=True)
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

        vals = dict(vals)
        if editing_plain and not editing_html:
            vals['gl_landingpage_html'] = plain_to_html(vals[source])
            editing_html = True

        result = super().write(vals)

        for event in self:
            if editing_html:
                current_html = event.gl_landingpage_html or ''
                updates = {}
                if source and 'gl_landingpage_html' in vals:
                    plain = html_to_plain(current_html)
                    if event[source] != plain:
                        updates[source] = plain
                if updates:
                    event._gl_internal_write(updates)
                if current_html:
                    # Saving the dedicated HTML field is explicit intent: preserve
                    # the former native value once, then publish the exact rich HTML.
                    event._gl_sync_html_to_native(backup=True)
            elif editing_native and event.gl_landingpage_native_linked:
                # Edits made directly in Odoo's website editor flow back into the
                # Groundlift HTML field and optional Studio plain-text mirror.
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
