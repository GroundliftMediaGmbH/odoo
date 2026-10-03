from lxml import etree

from odoo import api, fields, models
from odoo.tools.translate import html_translate


class EventEvent(models.Model):
    _inherit = 'event.event'

    # Deliberately a NEW field. It is not related to, computed from, or aliased to
    # Odoo's standard `description` field. Existing values are copied once by the
    # initializer below and this field becomes the master source afterwards.
    gl_event_public_html = fields.Html(
        string='Website HTML',
        translate=html_translate,
        sanitize_attributes=False,
        sanitize_form=False,
        help='HTML source used as the public event description on the website.',
    )

    # Stored separately so an intentionally emptied HTML field is never filled again
    # on a later module upgrade.
    gl_event_public_html_initialized = fields.Boolean(
        string='Website HTML initialized',
        default=False,
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        for vals in vals_list:
            vals = dict(vals)

            # If a record is created with an explicit HTML value, that value is the
            # master source immediately. Otherwise use the description Odoo would
            # receive on creation, if one is supplied.
            if 'gl_event_public_html' in vals:
                vals['description'] = vals.get('gl_event_public_html') or False
                vals['gl_event_public_html_initialized'] = True
            elif 'description' in vals:
                vals['gl_event_public_html'] = vals.get('description') or False
                vals['gl_event_public_html_initialized'] = True

            prepared_vals_list.append(vals)

        records = super().create(prepared_vals_list)

        # Odoo can create an event without an explicit description in vals and then
        # supply its default HTML. Initialise such new records from the final stored
        # standard value exactly once.
        for record in records.filtered(lambda event: not event.gl_event_public_html_initialized):
            record.with_context(gl_event_html_internal=True).write({
                'gl_event_public_html': record.description or False,
                'gl_event_public_html_initialized': True,
            })

        return records

    def write(self, vals):
        vals = dict(vals)

        # The new HTML field is the master source. Odoo's own event website already
        # renders `description`; mirroring here lets the standard website render our
        # HTML without inheriting or replacing any QWeb template.
        if (
            'gl_event_public_html' in vals
            and not self.env.context.get('gl_event_html_internal')
        ):
            vals['description'] = vals.get('gl_event_public_html') or False
            vals['gl_event_public_html_initialized'] = True

        return super().write(vals)

    @api.model
    def _gl_initialize_event_public_html(self):
        """Copy the current standard description into the new HTML field once.

        This method is called from XML data both on first installation and on module
        upgrades. The dedicated boolean prevents later upgrades from overwriting an
        HTML field that a user has edited or intentionally emptied.
        """
        events = self.sudo().with_context(active_test=False).search([
            ('gl_event_public_html_initialized', '=', False),
        ])
        if not events:
            return True

        languages = self.env['res.lang'].sudo().search([('active', '=', True)]).mapped('code')
        if not languages:
            languages = [self.env.lang]

        for event in events:
            # Copy every active translation independently. `description` is already
            # a native Odoo HTML field, so this preserves its actual stored HTML.
            for lang_code in languages:
                localized = event.with_context(lang=lang_code)
                source_html = localized.description or False
                localized.with_context(gl_event_html_internal=True).write({
                    'gl_event_public_html': source_html,
                })

            event.with_context(gl_event_html_internal=True).write({
                'gl_event_public_html_initialized': True,
            })

        return True

    @api.model
    def get_views(self, views, options=None):
        """Hide every occurrence of Odoo's standard description in event forms.

        The Groundlift database contains additional inherited/Studio views. Hiding
        the field after Odoo has assembled the final form architecture is more robust
        than an XPath that assumes where another module inserted `description`.
        """
        result = super().get_views(views, options)
        form_view = result.get('views', {}).get('form')
        if not form_view or not form_view.get('arch'):
            return result

        try:
            root = etree.fromstring(form_view['arch'].encode('utf-8'))
        except (etree.XMLSyntaxError, AttributeError):
            return result

        changed = False
        for node in root.xpath("//field[@name='description']"):
            node.set('invisible', 'True')
            changed = True

        for node in root.xpath("//label[@for='description']"):
            node.set('invisible', 'True')
            changed = True

        if changed:
            form_view['arch'] = etree.tostring(root, encoding='unicode')

        return result
