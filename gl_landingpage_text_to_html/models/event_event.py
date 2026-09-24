"""Keep the old Studio text field and a website-editable HTML field in sync.

We deliberately DO NOT redefine, rename, or delete the Studio source field.
The source field's technical name may vary between Groundlift databases.
"""

import logging

from odoo import api, fields, models

from .conversion import html_to_plain, plain_to_html

_logger = logging.getLogger(__name__)
PARAMETER = 'gl_landingpage_text_to_html.source_field'


class EventEvent(models.Model):
    _inherit = 'event.event'

    gl_landingpage_html = fields.Html(
        string='Landingpage Beschreibung (HTML)',
        sanitize=True,
        translate=False,
        copy=False,
        help='Formatierter Website-Text. Änderungen werden als Klartext in das bestehende Event-Beschreibungsfeld übertragen.',
    )

    @api.model
    def _gl_get_plain_field_name(self):
        """Use an explicit setting first; otherwise detect a UNIQUE Studio label.

        Failing closed (no guessing) is important: other event text fields must
        never be overwritten simply because their names look similar.
        """
        configured = self.env['ir.config_parameter'].sudo().get_param(PARAMETER, '').strip()
        if configured:
            f = self._fields.get(configured)
            if f and f.type == 'text' and configured != 'gl_landingpage_html':
                return configured
            _logger.warning('Landingpage Text_to_HTML: invalid source field %r (must be event.event text).', configured)
            return None
        hits = [
            name for name, field in self._fields.items()
            if field.type == 'text'
            and field.string.strip().casefold() in ('event beschreibung', 'eventbeschreibung')
        ]
        if len(hits) == 1:
            return hits[0]
        _logger.warning(
            'Landingpage Text_to_HTML: cannot unambiguously detect Event Beschreibung; '
            'set ir.config_parameter %s to the existing field technical name. Candidates: %s',
            PARAMETER, hits,
        )
        return None

    def _gl_fill_html_from_plain(self):
        source_field = self._gl_get_plain_field_name()
        for event in self:
            if source_field and not event.gl_landingpage_html and event[source_field]:
                event.with_context(gl_text_to_html_skip_sync=True).write({
                    'gl_landingpage_html': plain_to_html(event[source_field]),
                })

    def action_gl_copy_plain_to_html(self):
        """Manual recovery/backfill after the source field has been configured."""
        if not self._gl_get_plain_field_name():
            from odoo.exceptions import UserError
            from odoo import _
            raise UserError(_(
                'Quellfeld nicht erkannt. Bitte zuerst den Parameter '
                'gl_landingpage_text_to_html.source_field auf den technischen Namen '
                'des bestehenden Textfelds setzen.'
            ))
        self._gl_fill_html_from_plain()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        if self.env.context.get('gl_text_to_html_skip_sync'):
            return events
        source_field = self._gl_get_plain_field_name()
        if not source_field:
            return events
        for event, vals in zip(events, vals_list):
            if 'gl_landingpage_html' in vals:
                event.with_context(gl_text_to_html_skip_sync=True).write({
                    source_field: html_to_plain(event.gl_landingpage_html)
                })
            elif not event.gl_landingpage_html and event[source_field]:
                event.with_context(gl_text_to_html_skip_sync=True).write({
                    'gl_landingpage_html': plain_to_html(event[source_field])
                })
        return events

    def write(self, vals):
        if self.env.context.get('gl_text_to_html_skip_sync'):
            return super().write(vals)
        source_field = self._gl_get_plain_field_name()
        if not source_field or not ({source_field, 'gl_landingpage_html'} & vals.keys()):
            return super().write(vals)
        vals = dict(vals)
        if source_field in vals and 'gl_landingpage_html' not in vals:
            # The old text is still a valid entry point: refresh the website.
            vals['gl_landingpage_html'] = plain_to_html(vals[source_field])
            return super().write(vals)
        # The HTML editor is the last writer (also if both fields were supplied).
        # Read AFTER super() to mirror the already-sanitized stored value.
        result = super().write(vals)
        for event in self:
            text = html_to_plain(event.gl_landingpage_html)
            if event[source_field] != text:
                event.with_context(gl_text_to_html_skip_sync=True).write({source_field: text})
        return result
