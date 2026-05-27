# -*- coding: utf-8 -*-
from odoo import http, fields, _
from odoo.http import request


class GLServiceStaffPortal(http.Controller):

    @http.route(['/servicepersonal'], type='http', auth='public', website=True, methods=['GET', 'POST'], csrf=True)
    def service_staff_home(self, **post):
        member = False
        error = False
        if request.httprequest.method == 'POST':
            pin = (post.get('pin_code') or '').strip()
            member = request.env['gl.service.staff.member'].sudo().search([('pin_code', '=', pin), ('active', '=', True)], limit=1)
            if member:
                request.session['gl_service_staff_member_id'] = member.id
            else:
                request.session.pop('gl_service_staff_member_id', None)
                error = _('Der PIN-Code wurde nicht gefunden.')
        else:
            member_id = request.session.get('gl_service_staff_member_id')
            if member_id:
                member = request.env['gl.service.staff.member'].sudo().browse(member_id)
                if not member.exists() or not member.active:
                    member = False
                    request.session.pop('gl_service_staff_member_id', None)

        lines = request.env['gl.service.shift.line'].sudo()
        if member:
            lines = lines.search([
                ('member_id', '=', member.id),
                ('shift_id.active', '=', True),
                ('shift_id.shift_date', '>=', fields.Date.today()),
            ], order='planned_start_datetime asc, shift_id asc')
        return request.render('gl_service_staff.portal_service_staff_home', {
            'member': member,
            'lines': lines,
            'error': error,
        })

    @http.route(['/servicepersonal/logout'], type='http', auth='public', website=True, csrf=False)
    def service_staff_logout(self, **kw):
        request.session.pop('gl_service_staff_member_id', None)
        return request.redirect('/servicepersonal')

    @http.route(['/servicepersonal/antwort/<int:line_id>/<string:token>/<string:answer>'], type='http', auth='public', website=True, csrf=False)
    def service_staff_response(self, line_id, token, answer, **kw):
        line = request.env['gl.service.shift.line'].sudo().search([('id', '=', line_id), ('token', '=', token)], limit=1)
        if not line:
            return request.render('gl_service_staff.portal_service_staff_response', {
                'success': False,
                'title': _('Link ungültig'),
                'message': _('Dieser Antwort-Link ist ungültig oder nicht mehr vorhanden.'),
                'line': False,
            })
        if answer == 'accept':
            line._accept(source='public')
            title = _('Zusage gespeichert')
            message = _('Vielen Dank! Deine Zusage wurde gespeichert.')
            success = True
        elif answer == 'decline':
            line._decline(source='public')
            title = _('Absage gespeichert')
            message = _('Danke für deine Rückmeldung. Deine Absage wurde gespeichert.')
            success = True
        else:
            title = _('Antwort unbekannt')
            message = _('Diese Antwort konnte nicht verarbeitet werden.')
            success = False
        return request.render('gl_service_staff.portal_service_staff_response', {
            'success': success,
            'title': title,
            'message': message,
            'line': line,
        })

    @http.route(['/servicepersonal/overview'], type='http', auth='public', website=True, csrf=False)
    def service_staff_overview(self, **kw):
        shifts = request.env['gl.service.shift'].sudo().search([
            ('active', '=', True),
            ('shift_date', '>=', fields.Date.today()),
        ], order='shift_date asc, start_datetime asc')
        return request.render('gl_service_staff.portal_service_staff_overview', {
            'shifts': shifts,
        })
