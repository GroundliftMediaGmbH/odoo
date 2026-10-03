"""Neutralize the obsolete inherited website view before Odoo validates views.

Older versions created the QWeb view
``gl_landingpage_text_to_html.gl_landingpage_event_description_html``.
Its XPath no longer matches the current/customized website_event parent view.

Merely setting ``active = false`` is NOT sufficient during a module upgrade:
Odoo 19 validates the module's own ir.ui.view records at the end of the upgrade,
and an inactive inherited view can therefore still fail while its inheritance
is resolved.  We must break the inheritance itself *before* module data is
loaded/validated.

This script uses SQL intentionally: ORM writes to ir.ui.view would validate the
old broken architecture before the repair is complete.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_ui_view AS v
           SET active = FALSE,
               inherit_id = NULL,
               mode = 'primary',
               arch_fs = NULL,
               arch_updated = TRUE
          FROM ir_model_data AS d
         WHERE d.module = %s
           AND d.name = %s
           AND d.model = 'ir.ui.view'
           AND d.res_id = v.id
        """,
        ('gl_landingpage_text_to_html', 'gl_landingpage_event_description_html'),
    )
