"""Remove the obsolete Groundlift website QWeb inheritance before view loading.

Older module versions created the view XML-ID
``gl_landingpage_text_to_html.gl_landingpage_event_description_html`` and
stored its source path in ``ir_ui_view.arch_fs``.  The parent website_event
view changed/customized on this database, so that legacy XPath can no longer
be resolved during an automatic Odoo.sh module upgrade.

This pre-migration intentionally uses only SQL.  It runs before the new module
data are loaded, and therefore before Odoo can try to validate the obsolete
inheritance again.
"""
import logging

_logger = logging.getLogger(__name__)

MODULE = 'gl_landingpage_text_to_html'
XMLID = 'gl_landingpage_event_description_html'
LEGACY_ARCH_FS = f'{MODULE}/views/website_event_templates.xml'


def migrate(cr, version):
    # Upgrade scripts normally only run on updates, but keep this safe if the
    # loader ever calls it without an installed source version.
    if not version:
        return

    # Find both the module-owned XML-ID and possible stale file-backed copies.
    cr.execute(
        """
        SELECT DISTINCT v.id, v.inherit_id
          FROM ir_ui_view v
          LEFT JOIN ir_model_data d
            ON d.model = 'ir.ui.view' AND d.res_id = v.id
         WHERE (d.module = %s AND d.name = %s)
            OR v.arch_fs = %s
        """,
        (MODULE, XMLID, LEGACY_ARCH_FS),
    )
    legacy_views = cr.fetchall()

    for view_id, parent_id in legacy_views:
        # In the unlikely case that another customization inherits our old
        # helper view, keep that customization attached to the old parent
        # rather than leaving a dangling inheritance chain.
        cr.execute(
            "UPDATE ir_ui_view SET inherit_id = %s WHERE inherit_id = %s",
            (parent_id, view_id),
        )

        # Direct SQL avoids ir.ui.view constraints while the old XPath is still
        # invalid.  Clearing arch_fs is important: otherwise Odoo can still
        # associate the DB record with the deleted XML source file.
        cr.execute(
            """
            UPDATE ir_ui_view
               SET active = FALSE,
                   inherit_id = NULL,
                   mode = 'primary',
                   arch_fs = NULL
             WHERE id = %s
            """,
            (view_id,),
        )

    # The XML-ID no longer exists in the module.  Removing the mapping means
    # Odoo's module data cleanup/validation cannot treat the obsolete DB view
    # as a current view belonging to this module.
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = %s
           AND name = %s
           AND model = 'ir.ui.view'
        """,
        (MODULE, XMLID),
    )

    if legacy_views:
        _logger.info(
            'Landingpage Text_to_HTML: neutralized %d obsolete website view(s).',
            len(legacy_views),
        )
