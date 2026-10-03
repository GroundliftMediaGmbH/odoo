"""One-shot repair for the obsolete Groundlift website-event QWeb view.

This module is a dependency of gl_landingpage_text_to_html.  Therefore Odoo
installs it before upgrading the main module.  Its pre-init hook runs before
any data of the main module are loaded/validated and neutralizes the stale
ir.ui.view row left by older versions.
"""
import logging

_logger = logging.getLogger(__name__)

OLD_MODULE = 'gl_landingpage_text_to_html'
OLD_XMLID = 'gl_landingpage_event_description_html'
OLD_ARCH_FS = f'{OLD_MODULE}/views/website_event_templates.xml'
OLD_VIEW_NAME = 'Groundlift event page: HTML description only'


def pre_init_hook(env):
    cr = env.cr

    # Find the exact obsolete row through multiple independent fingerprints.
    cr.execute(
        """
        SELECT DISTINCT v.id, v.inherit_id
          FROM ir_ui_view v
          LEFT JOIN ir_model_data d
            ON d.model = 'ir.ui.view' AND d.res_id = v.id
         WHERE (d.module = %s AND d.name = %s)
            OR v.arch_fs = %s
            OR (v.name = %s AND v.inherit_id IS NOT NULL)
        """,
        (OLD_MODULE, OLD_XMLID, OLD_ARCH_FS, OLD_VIEW_NAME),
    )
    rows = cr.fetchall()

    for view_id, parent_id in rows:
        # Keep any third-party child customization alive by attaching it to the
        # former parent of the obsolete helper view.
        cr.execute(
            "UPDATE ir_ui_view SET inherit_id = %s WHERE inherit_id = %s",
            (parent_id, view_id),
        )

        # Neutralize the stale view without invoking ORM/QWeb validation.
        # The invalid XPath may remain in arch_db, but with no inheritance,
        # primary mode, inactive state and no module XML-ID it is never resolved
        # or validated as part of the Groundlift module upgrade.
        cr.execute(
            """
            UPDATE ir_ui_view
               SET active = FALSE,
                   inherit_id = NULL,
                   mode = 'primary',
                   arch_fs = NULL,
                   key = NULL
             WHERE id = %s
            """,
            (view_id,),
        )

    # Most important for Odoo's module-level view validation: the obsolete row
    # must no longer belong to gl_landingpage_text_to_html.
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = %s
           AND name = %s
           AND model = 'ir.ui.view'
        """,
        (OLD_MODULE, OLD_XMLID),
    )

    _logger.warning(
        'Groundlift landingpage repair: neutralized %s obsolete website view(s).',
        len(rows),
    )
