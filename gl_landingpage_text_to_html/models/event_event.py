"""Groundlift event description bridge for Odoo 19.

The design is intentionally simple and does not inherit any website QWeb view:

* the existing Groundlift plain-text event description remains the source when
  it is edited;
* ``gl_landingpage_html`` is the editable rich-text representation;
* Odoo's native ``event.event.description`` is always kept identical to the
  rich HTML, so Odoo's normal public event page renders exactly that HTML.

This avoids XPath dependencies on Odoo/Studio website templates altogether.
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
    """Compatibility helper retained for the module's regression tests."""
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
            'Bearbeitbare HTML-Version der Eventbeschreibung. Diese Version '
            'wird 1:1 in die native Odoo-Webseitenbeschreibung gespiegelt.'
        ),
    )
    # Kept for compatibility with already installed versions of this module.
    gl_landingpage_native_linked = fields.Boolean(
        string='Mit Odoo-Webseitenbeschreibung verbunden',
        copy=False,
        help='Technischer Status: event.description entspricht Landingpage HTML.',
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
                event.gl_landingpage_website_status = _('HTML-Beschreibung ist noch leer.')
            elif html == native:
                event.gl_landingpage_website_status = _(
                    'OK – die Odoo-Veranstaltungsseite verwendet exakt diese HTML-Version.'
                )
            else:
                event.gl_landingpage_website_status = _(
                    'Abweichung erkannt – bitte „HTML jetzt auf Odoo-Webseite übernehmen“ klicken.'
                )

    @api.model
    def _gl_get_plain_field_name(self):
        """Locate the existing Groundlift/Studio plain-text event field."""
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
            'Landingpage Text_to_HTML: source field ambiguous/not found; set %s. Matches: %s',
            PARAMETER, hits,
        )
        return None

    @api.model
    def _gl_prepare_synced_vals(self, vals):
        """Mirror whichever description representation was explicitly edited.

        Priority when multiple fields arrive in one write:
        1) Landingpage HTML
        2) existing Groundlift plain-text field
        3) native Odoo description (e.g. website inline editor)
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
        return super().create([self._gl_prepare_synced_vals(v) for v in vals_list])

    def write(self, vals):
        if self.env.context.get(SKIP_SYNC):
            return super().write(vals)

        source = self._gl_get_plain_field_name()
        relevant = (
            'gl_landingpage_html' in vals
            or 'description' in vals
            or bool(source and source in vals)
        )
        if not relevant:
            return super().write(vals)

        # Preserve a differing old native description once before an explicit
        # rich-HTML edit replaces it.
        if 'gl_landingpage_html' in vals:
            incoming = vals.get('gl_landingpage_html') or ''
            for event in self:
                if (
                    event.description
                    and event.description != incoming
                    and not event.gl_landingpage_native_backup
                ):
                    super(EventEvent, event.with_context(**{SKIP_SYNC: True})).write({
                        'gl_landingpage_native_backup': event.description,
                    })

        return super().write(self._gl_prepare_synced_vals(vals))

    def _gl_force_html_to_public_description(self):
        """Backfill old records and make Landingpage HTML canonical publicly."""
        source = self._gl_get_plain_field_name()
        for event in self:
            html = event.gl_landingpage_html or ''

            if not html:
                if source and event[source]:
                    html = plain_to_html(event[source])
                elif event.description:
                    # Preserve native HTML if no Groundlift source can be found.
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

            event.with_context(**{SKIP_SYNC: True}).write(updates)

    @api.model
    def _gl_migrate_existing(self):
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
                'Quellfeld nicht erkannt. Bitte den Systemparameter '
                'gl_landingpage_text_to_html.source_field auf den technischen '
                'Namen des bestehenden event.event-Textfelds setzen.'
            ))
        for event in self:
            if not event.gl_landingpage_html and event[source]:
                event.write({'gl_landingpage_html': plain_to_html(event[source])})
        return True

    def action_gl_sync_native_if_safe(self):
        # Compatibility for the button used by older XML versions.
        self._gl_force_html_to_public_description()
        return True

    def action_gl_force_native_link(self):
        self._gl_force_html_to_public_description()
        return True
