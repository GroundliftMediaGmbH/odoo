"""Remove the obsolete Groundlift website QWeb view before module data loading.

Important: older recovery versions changed ir_ui_view with raw SQL but did not
invalidate the ORM cache afterwards.  During the same registry rebuild Odoo
could therefore still validate the cached, obsolete XPath.  This migration
neutralizes the row and explicitly invalidates the environment cache before
normal module XML is loaded.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MODULE = 'gl_landingpage_text_to_html'
XMLID = 'gl_landingpage_event_description_html'
LEGACY_ARCH_FS = f'{MODULE}/views/website_event_templates.xml'
LEGACY_NAMES = (
    'Groundlift event page: HTML description only',
    'Landingpage HTML event description',
)


def _find_legacy_views(cr):
    cr.execute(
        """
        SELECT DISTINCT v.id, v.inherit_id
          FROM ir_ui_view v
          LEFT JOIN ir_model_data d
            ON d.model = 'ir.ui.view' AND d.res_id = v.id
         WHERE (d.module = %s AND d.name = %s)
            OR v.arch_fs = %s
            OR v.name = ANY(%s)
            OR CAST(v.arch_db AS TEXT) LIKE %s
        """,
        (
            MODULE,
            XMLID,
            LEGACY_ARCH_FS,
            list(LEGACY_NAMES),
            '%o_wevent_event_main_col%',
        ),
    )
    return cr.fetchall()


def _neutralize(cr, rows):
    for view_id, parent_id in rows:
        # If anything inherited our old helper view, keep it attached to the
        # helper's former parent instead of leaving a broken chain.
        cr.execute(
            "UPDATE ir_ui_view SET inherit_id = %s WHERE inherit_id = %s AND id <> %s",
            (parent_id, view_id, view_id),
        )

        # Make the stale record harmless without invoking ir.ui.view ORM
        # constraints while its historical XPath is still invalid.
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

        # Remove every external-id mapping that points to this obsolete helper
        # view.  It must no longer be considered module data during validation.
        cr.execute(
            "DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id = %s",
            (view_id,),
        )


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    env.flush_all()

    rows = _find_legacy_views(cr)
    _neutralize(cr, rows)

    # Critical difference versus v1.8/v1.9/v2.0: discard cached values for
    # ir.ui.view / ir.model.data before Odoo continues loading this module.
    env.invalidate_all()

    _logger.warning(
        'Landingpage Text_to_HTML v2.1: neutralized %d legacy QWeb view(s) and invalidated ORM cache.',
        len(rows),
    )
