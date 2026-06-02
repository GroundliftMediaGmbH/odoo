# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class GlAppFoldersController(http.Controller):
    @http.route('/gl_app_folders/desktop', type='http', auth='user')
    def gl_app_folders_desktop(self, **kwargs):
        action = request.env.ref('gl_app_folders.action_gl_app_folders_desktop', raise_if_not_found=False)
        if action:
            return request.redirect(f'/odoo/action-{action.id}')
        return request.redirect('/odoo')
