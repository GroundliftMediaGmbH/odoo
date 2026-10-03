"""Disable the obsolete inherited website view before Odoo loads module data.

Earlier releases inherited website_event.event_description_full with an XPath.
That is exactly what caused the RPC ParseError on customized Odoo databases.
v1.6 does not inherit the website view at all; the standard page receives the
canonical HTML through event.event.description instead.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_ui_view
           SET active = FALSE
         WHERE id IN (
               SELECT res_id
                 FROM ir_model_data
                WHERE module = %s
                  AND name = %s
                  AND model = 'ir.ui.view'
         )
        """,
        ('gl_landingpage_text_to_html', 'gl_landingpage_event_description_html'),
    )
