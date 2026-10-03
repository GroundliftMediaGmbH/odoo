from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    data = env['ir.model.data'].sudo().search([
        ('module', '=', 'gl_landingpage_text_to_html'),
        ('name', '=', 'gl_landingpage_event_description_html'),
        ('model', '=', 'ir.ui.view'),
    ], limit=1)
    if data and data.res_id:
        view = env['ir.ui.view'].sudo().browse(data.res_id).exists()
        if view:
            view.with_context(active_test=False).write({'active': False})
    env['event.event'].sudo()._gl_migrate_existing()
