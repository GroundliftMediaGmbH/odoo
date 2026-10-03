"""One-shot database repair for the stale Groundlift Landingpage QWeb view.

This module has a NEW technical name on purpose. Installing it guarantees that
its post-init hook runs even if one of the older repair modules is already
installed. It is installed separately BEFORE upgrading the main module.
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


def _find_rows(cr):
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


def post_init_hook(env):
    # Odoo 19 passes an Environment to post_init_hook.
    env = api.Environment(env.cr, SUPERUSER_ID, {})
    cr = env.cr
    env.flush_all()

    rows = _find_rows(cr)
    ids = []
    for view_id, parent_id in rows:
        ids.append(view_id)
        cr.execute(
            "UPDATE ir_ui_view SET inherit_id = %s WHERE inherit_id = %s AND id <> %s",
            (parent_id, view_id, view_id),
        )
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
        cr.execute(
            "DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id = %s",
            (view_id,),
        )

    # The old failures persisted because raw SQL left stale ir.ui.view cache
    # entries alive during the same registry rebuild. Clear the cache now.
    env.invalidate_all()

    result = f'fixed={len(ids)}; ids={ids}'
    env['ir.config_parameter'].sudo().set_param(
        'gl_landingpage_emergency_repair_21.result', result
    )
    _logger.warning('Groundlift Landingpage Emergency Repair 2.1: %s', result)
