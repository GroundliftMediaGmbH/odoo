"""Groundlift landing-page HTML bridge for Odoo 19.

Design of v1.4:
- the existing Groundlift/Studio plain-text event description remains available;
- that plain text is mirrored into ``gl_landingpage_html`` as editable HTML;
- edits in the HTML field are mirrored back to the plain-text field;
- ``gl_landingpage_html`` is the canonical website content;
- Odoo's native ``event.description`` is kept byte-for-byte in sync as a
  compatibility fallback for third-party/custom event templates.

The public website template shipped with this module renders ONLY
``gl_landingpage_html``.  The native field is synchronized deliberately so that
an unrelated Groundlift website override which still references
``event.description`` cannot expose an old/plain version of the text.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .conversion import html_to_plain, plain_to_html

_logger = logging.getLogger(__name__)
PARAMETER = 'gl_landingpage_text_to_html.source_field'
SKIP_SYNC = 'gl_text_to_html_skip_sync'


class EventEvent(models.Model):
    _inherit = 'event.event'

    gl_landingpage_html = fields.Html(
        string='Landingpage Beschreibung (HTML)',
        sanitize=True,
        translate=False,
        copy=False,
        help='Formatierte Beschreibung für die öffentliche Veranstaltungsseite.',
    )

    # Kept for database compatibility with v1.2/v1.3.  In v1.4 the fields no
    # longer control whether website content is synchronized: synchronization
    # is intentionally unconditional.
    gl_landingpage_native_linked = fields.Boolean(
        string='Mit Odoo-Webseitenbeschreibung verbunden',
        copy=False,
        default=True,
    )
    gl_landingpage_native_backup = fields.Html(
        string='Sicherung der vorherigen Odoo-Webseitenbeschreibung',
        sanitize=True,
        translate=False,
        copy=False,
        groups='base.group_system',
    )
    gl_landingpage_website_status = fields.Char(
        string='Website-Status',
        compute='_compute_gl_landingpage_website_status',
    )

    @api.depends('gl_landingpage_html', 'description')
    def _compute_gl_landingpage_website_status(self):
        for event in self:
            if not event.gl_landingpage_html:
                event.gl_landingpage_website_status = _('HTML-Beschreibung ist noch leer.')
            elif event.description == event.gl_landingpage_html:
                event.gl_landingpage_website_status = _(
                    'Landingpage HTML ist aktiv und mit der Website synchron.'
                )
            else:
                event.gl_landingpage_website_status = _(
                    'Landingpage HTML ist aktiv. Beim nächsten Speichern wird der Website-Fallback synchronisiert.'
                )

    @api.model
    def _gl_get_plain_field_name(self):
        """Return the existing Groundlift/Studio plain-text description field.

        The technical field name can be pinned through the existing system
        parameter.  Otherwise we retain the exact v1.2 discovery behaviour.
        """
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
        """Bypass only this module's own mirror logic, not other model hooks."""
        return self.with_context(**{SKIP_SYNC: True}).write(vals)

    def _gl_fill_html_from_plain(self, force=False):
        """Create HTML from the original plain-text field.

        Existing rich HTML is preserved unless ``force`` is explicitly used.
        This is important on upgrades because handcrafted formatting in the HTML
        tab must never be destroyed simply because the module is updated.
        """
        source = self._gl_get_plain_field_name()
        if not source:
            return
        for event in self:
            if event[source] and (force or not event.gl_landingpage_html):
                event._gl_internal_write({
                    'gl_landingpage_html': plain_to_html(event[source]),
                })

    def _gl_sync_website_fallback(self):
        """Keep native ``description`` identical to the canonical HTML.

        This is intentionally unconditional.  The actual Groundlift event page
        renders ``gl_landingpage_html`` directly; this mirror merely makes the
        result robust against other installed templates that still output
        ``event.description``.
        """
        for event in self:
            html = event.gl_landingpage_html or ''
            vals = {'gl_landingpage_native_linked': True}
            if (event.description or '') != html:
                vals['description'] = html
            event._gl_internal_write(vals)

    def action_gl_copy_plain_to_html(self):
        source = self._gl_get_plain_field_name()
        if not source:
            raise UserError(_(
                'Quellfeld nicht erkannt. Systemparameter '
                'gl_landingpage_text_to_html.source_field auf den technischen '
                'Namen des bestehenden event.event-Textfelds setzen.'
            ))
        # Preserve the v1.2 button semantics: only fill when HTML is empty.
        self._gl_fill_html_from_plain(force=False)
        self._gl_sync_website_fallback()
        return True

    # Compatibility actions retained so existing button/action references from
    # older databases do not break.  Both now simply enforce the v1.4 model.
    def action_gl_sync_native_if_safe(self):
        self._gl_fill_html_from_plain(force=False)
        self._gl_sync_website_fallback()
        return True

    def action_gl_force_native_link(self):
        self._gl_fill_html_from_plain(force=False)
        for event in self:
            if not event.gl_landingpage_html:
                raise UserError(_('Bitte zuerst eine Landingpage-HTML-Beschreibung eintragen.'))
        self._gl_sync_website_fallback()
        return True

    @api.model
    def _gl_migrate_existing(self):
        """Backfill existing events without destroying handcrafted HTML.

        Called by the install hook and by the v1.4 migration script.  Existing
        ``gl_landingpage_html`` wins; only empty HTML fields are generated from
        the old plain-text field.  Afterwards the compatibility fallback is
        forced to that same HTML for every event.
        """
        events = self.sudo()
        last_id = 0
        while True:
            batch = events.search([('id', '>', last_id)], order='id', limit=200)
            if not batch:
                break
            batch._gl_fill_html_from_plain(force=False)
            batch._gl_sync_website_fallback()
            last_id = batch[-1].id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get(SKIP_SYNC):
            return records

        source = self._gl_get_plain_field_name()
        for event, incoming in zip(records, vals_list):
            if incoming.get('gl_landingpage_html'):
                html = event.gl_landingpage_html or ''
                updates = {}
                if source:
                    plain = html_to_plain(html)
                    if event[source] != plain:
                        updates[source] = plain
                if (event.description or '') != html:
                    updates['description'] = html
                updates['gl_landingpage_native_linked'] = True
                if updates:
                    event._gl_internal_write(updates)
            elif source and event[source]:
                event._gl_fill_html_from_plain(force=False)
                event._gl_sync_website_fallback()
            elif event.description and not event.gl_landingpage_html:
                # Last-resort compatibility for events created by standard Odoo
                # without the Groundlift plain field populated.
                event._gl_internal_write({
                    'gl_landingpage_html': event.description,
                    'gl_landingpage_native_linked': True,
                })
        return records

    def write(self, vals):
        if self.env.context.get(SKIP_SYNC):
            return super().write(vals)

        source = self._gl_get_plain_field_name()
        editing_html = 'gl_landingpage_html' in vals
        editing_plain = bool(source and source in vals)
        editing_native = 'description' in vals

        # Ordinary event changes must remain untouched.
        if not (editing_html or editing_plain or editing_native):
            return super().write(vals)

        vals = dict(vals)

        # Plain text -> HTML: whenever the original text is edited, rebuild the
        # HTML unless the caller explicitly supplied an HTML value in the same
        # write operation.
        if editing_plain and not editing_html:
            vals['gl_landingpage_html'] = plain_to_html(vals.get(source) or '')
            editing_html = True

        # HTML -> plain text + native fallback.  This happens in the same write
        # so every successfully saved HTML edit immediately reaches the page.
        if editing_html:
            html = vals.get('gl_landingpage_html') or ''
            vals['description'] = html
            vals['gl_landingpage_native_linked'] = True
            if source and not editing_plain:
                vals[source] = html_to_plain(html)
            return super().write(vals)

        # A direct edit of Odoo's native website description is treated as an
        # HTML edit as well.  This keeps old inline-editor/custom-module flows
        # compatible while still making gl_landingpage_html canonical afterwards.
        if editing_native:
            html = vals.get('description') or ''
            vals['gl_landingpage_html'] = html
            vals['gl_landingpage_native_linked'] = True
            if source:
                vals[source] = html_to_plain(html)
            return super().write(vals)

        return super().write(vals)
