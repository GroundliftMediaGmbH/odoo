"""Groundlift event description bridge for Odoo 19.

Design of v1.6
===============
* The existing Groundlift plain-text field remains available.
* ``gl_landingpage_html`` is the editable rich-text version and the canonical
  content for the public event page.
* Odoo's native ``event.event.description`` is kept as an exact mirror of the
  HTML field because Odoo's standard event website renders that native field.
* There is deliberately NO inherited website/QWeb template and therefore NO
  XPath against ``website_event``.  This avoids the installation failures that
  occurred when another website view changed Odoo's surrounding HTML.

Changes made in any of the three fields are mirrored immediately.  When more
than one field is present in the same write, explicit Groundlift HTML wins,
then the Groundlift plain-text field, then Odoo's native description.
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
        help=(
            'Formatierte Beschreibung. Diese HTML-Version ist die führende '
            'Version für die öffentliche Odoo-Veranstaltungsseite.'
        ),
    )
    # Keep the old technical fields for a clean upgrade from earlier versions.
    gl_landingpage_native_linked = fields.Boolean(
        string='Mit Odoo-Webseitenbeschreibung verbunden',
        copy=False,
        help='Technischer Status: Odoo event.description spiegelt Landingpage HTML.',
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
            html = event.gl_landingpage_html or ''
            native = event.description or ''
            if not html:
                event.gl_landingpage_website_status = _(
                    'HTML-Beschreibung ist noch leer.'
                )
            elif html == native:
                event.gl_landingpage_website_status = _(
                    'OK – die öffentliche Odoo-Veranstaltungsseite zeigt diese HTML-Version.'
                )
            else:
                # This should only be visible if another module changed
                # description with our synchronization context explicitly off.
                event.gl_landingpage_website_status = _(
                    'Abweichung erkannt – bitte „HTML jetzt auf Odoo-Webseite übernehmen“ klicken.'
                )

    @api.model
    def _gl_get_plain_field_name(self):
        """Return Groundlift's existing Studio plain-text field, if identifiable."""
        configured = self.env['ir.config_parameter'].sudo().get_param(PARAMETER, '').strip()
        if configured:
            field = self._fields.get(configured)
            if field and field.type == 'text' and configured != 'description':
                return configured
            _logger.warning(
                'Landingpage Text_to_HTML: invalid Studio source field %r.', configured
            )
            return None

        hits = [
            name for name, field in self._fields.items()
            if field.type == 'text'
            and (field.string or '').strip().casefold() in (
                'event beschreibung', 'eventbeschreibung'
            )
        ]
        if len(hits) == 1:
            return hits[0]
        _logger.warning(
            'Landingpage Text_to_HTML: ambiguous Studio source field; set %s (matches: %s).',
            PARAMETER, hits,
        )
        return None

    def _gl_internal_write(self, vals):
        """Write without entering this bridge again."""
        return self.with_context(**{SKIP_SYNC: True}).write(vals)

    @api.model
    def _gl_synchronized_vals(self, vals):
        """Return *vals* extended so all description representations agree.

        Priority for simultaneous inputs:
        1. gl_landingpage_html (explicit rich-text edit)
        2. Groundlift legacy plain-text field
        3. Odoo native description (e.g. website inline editor)
        """
        vals = dict(vals)
        source = self._gl_get_plain_field_name()

        if 'gl_landingpage_html' in vals:
            html = vals.get('gl_landingpage_html') or ''
            vals['description'] = html
            vals['gl_landingpage_native_linked'] = bool(html)
            if source:
                vals[source] = html_to_plain(html)
            return vals

        if source and source in vals:
            html = plain_to_html(vals.get(source) or '')
            vals['gl_landingpage_html'] = html
            vals['description'] = html
            vals['gl_landingpage_native_linked'] = bool(html)
            return vals

        if 'description' in vals:
            html = vals.get('description') or ''
            vals['gl_landingpage_html'] = html
            vals['gl_landingpage_native_linked'] = bool(html)
            if source:
                vals[source] = html_to_plain(html)

        return vals

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get(SKIP_SYNC):
            return super().create(vals_list)
        synchronized = [self._gl_synchronized_vals(vals) for vals in vals_list]
        return super().create(synchronized)

    def write(self, vals):
        if self.env.context.get(SKIP_SYNC):
            return super().write(vals)

        touches_description = (
            'gl_landingpage_html' in vals
            or 'description' in vals
        )
        source = self._gl_get_plain_field_name()
        if source and source in vals:
            touches_description = True

        if not touches_description:
            return super().write(vals)

        # Preserve an older native description once before the canonical HTML
        # overwrites it.  This is only a safety net for upgrades/manual edits.
        if 'gl_landingpage_html' in vals:
            incoming_html = vals.get('gl_landingpage_html') or ''
            for event in self:
                if (
                    event.description
                    and event.description != incoming_html
                    and not event.gl_landingpage_native_backup
                ):
                    event._gl_internal_write({
                        'gl_landingpage_native_backup': event.description,
                    })

        return super().write(self._gl_synchronized_vals(vals))

    def _gl_force_html_to_public_description(self):
        """Make HTML canonical for existing records, preserving prior native HTML once."""
        source = self._gl_get_plain_field_name()
        for event in self:
            html = event.gl_landingpage_html or ''

            # Initial fill: existing Groundlift plain text -> HTML.  If no
            # Groundlift source can be discovered, preserve Odoo's native HTML.
            if not html:
                if source and event[source]:
                    html = plain_to_html(event[source])
                elif event.description:
                    html = event.description

            if not html:
                continue

            updates = {
                'gl_landingpage_html': html,
                'description': html,
                'gl_landingpage_native_linked': True,
            }
            if source:
                plain = html_to_plain(html)
                if event[source] != plain:
                    updates[source] = plain

            if (
                event.description
                and event.description != html
                and not event.gl_landingpage_native_backup
            ):
                updates['gl_landingpage_native_backup'] = event.description

            event._gl_internal_write(updates)

    @api.model
    def _gl_migrate_existing(self):
        """Backfill and force the canonical HTML onto all existing event pages."""
        events = self.sudo()
        last_id = 0
        while True:
            batch = events.search([('id', '>', last_id)], order='id', limit=200)
            if not batch:
                break
            batch._gl_force_html_to_public_description()
            last_id = batch[-1].id

    def action_gl_copy_plain_to_html(self):
        source = self._gl_get_plain_field_name()
        if not source:
            raise UserError(_(
                'Quellfeld nicht erkannt. Systemparameter '
                'gl_landingpage_text_to_html.source_field auf den technischen '
                'Namen des bestehenden event.event-Textfelds setzen.'
            ))
        for event in self:
            if not event.gl_landingpage_html and event[source]:
                # Normal write intentionally mirrors HTML -> native description.
                event.write({'gl_landingpage_html': plain_to_html(event[source])})
        return True

    def action_gl_sync_native_if_safe(self):
        # Kept for compatibility with the old backend button/XML ID.  v1.6 no
        # longer has a "safe vs force" distinction: HTML is intentionally the
        # canonical public version.
        self._gl_force_html_to_public_description()
        return True

    def action_gl_force_native_link(self):
        self._gl_force_html_to_public_description()
        return True
