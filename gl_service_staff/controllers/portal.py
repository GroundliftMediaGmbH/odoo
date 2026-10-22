# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import http, fields, _
from odoo.http import request

from ..calendar_feed import build_calendar_feed


def _service_portal_clock_time(value, record):
    """Return only HH:MM (Europe/Berlin) for a coworker's shift time."""
    if not value:
        return ''
    localized = fields.Datetime.context_timestamp(
        record.with_context(tz='Europe/Berlin'),
        fields.Datetime.to_datetime(value),
    )
    return localized.strftime('%H:%M')


def _service_portal_line_sort_key(line):
    """Sort by the date/time the employee *actually sees* in the portal.

    The portal template displays ``planned_start_datetime`` when present;
    otherwise it displays only ``shift_date``. Do not fall back to the
    shift's ``start_datetime``: legacy/project records can hold a different
    (or stale) year there, placing date-only projects after later events.
    
    Both cases are normalized to Europe/Berlin wall-clock time, so a
    date-only project appears at 00:00 on its displayed day among events.
    """
    if line.planned_start_datetime:
        effective_start = fields.Datetime.context_timestamp(
            line.with_context(tz='Europe/Berlin'),
            fields.Datetime.to_datetime(line.planned_start_datetime),
        ).replace(tzinfo=None)
    else:
        # shift_date is required on gl.service.shift and is precisely the
        # date shown by the project's date-only portal tile.
        effective_start = datetime.combine(
            fields.Date.to_date(line.shift_id.shift_date), time.min,
        )
    return effective_start, line.shift_id.id, line.id


class GLServiceStaffPortal(http.Controller):

    @http.route(
        ['/servicepersonal'], type='http', auth='public', website=True,
        methods=['GET', 'POST'], csrf=True
    )
    def service_staff_home(self, **post):
        member = False
        error = False
        if request.httprequest.method == 'POST':
            pin = (post.get('pin_code') or '').strip()
            member = request.env['gl.service.staff.member'].sudo().search([
                ('pin_code', '=', pin), ('active', '=', True)
            ], limit=1)
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
        coworkers_by_line = {}
        calendar_url = False
        if member:
            member._ensure_calendar_token()
            calendar_url = member.calendar_url
            lines = lines.search([
                ('member_id', '=', member.id),
                ('shift_id.active', '=', True),
                ('shift_id.shift_date', '>=', fields.Date.context_today(member)),
                ('state', '!=', 'draft'),
            ])
            # Sort projects AND events as one list by the date/time visibly
            # shown on their cards (including projects with date-only times).
            lines = lines.sorted(key=_service_portal_line_sort_key)
            for line in lines:
                others = line.shift_id.line_ids.filtered(
                    lambda other: other.state == 'accepted' and other.role == 'desired'
                    and other.member_id.employee_id != member.employee_id
                )
                seen_employees = set()
                people = []
                for other in others.sorted(key=lambda rec: (rec.member_id.name or '').casefold()):
                    employee = other.member_id.employee_id
                    if employee.id in seen_employees:
                        continue
                    seen_employees.add(employee.id)
                    people.append({
                        'name': other.member_id.name,
                        'start': _service_portal_clock_time(other.planned_start_datetime, other),
                        'end': _service_portal_clock_time(other.planned_end_datetime, other),
                    })
                coworkers_by_line[line.id] = people
        return request.render('gl_service_staff.portal_service_staff_home', {
            'member': member,
            'lines': lines,
            'coworkers_by_line': coworkers_by_line,
            'calendar_url': calendar_url,
            'error': error,
        })

    @http.route(
        ['/servicepersonal/kalender/<int:member_id>/<string:token>.ics'],
        type='http', auth='public', website=False, methods=['GET'], csrf=False
    )
    def service_staff_calendar_feed(self, member_id, token, **kw):
        member = request.env['gl.service.staff.member'].sudo().search([
            ('id', '=', member_id), ('calendar_token', '=', token), ('active', '=', True),
        ], limit=1)
        if not member:
            return request.not_found()
        lines = request.env['gl.service.shift.line'].sudo().search([
            ('member_id', '=', member.id),
            ('state', '=', 'accepted'),
            ('role', '=', 'desired'),
            ('shift_id.active', '=', True),
        ], order='planned_start_datetime asc, id asc')
        content = build_calendar_feed(lines)
        return request.make_response(content, headers=[
            ('Content-Type', 'text/calendar; charset=utf-8'),
            ('Content-Disposition', 'inline; filename="groundlift-service.ics"'),
            ('Cache-Control', 'private, no-store, no-cache, must-revalidate'),
            ('X-Robots-Tag', 'noindex, nofollow, noarchive'),
            ('Referrer-Policy', 'no-referrer'),
        ])

    @http.route(
        ['/servicepersonal/mitarbeiter/<int:member_id>/<string:pin_code>'],
        type='http', auth='public', website=True, csrf=False
    )
    def service_staff_member_direct(self, member_id, pin_code, **kw):
        member = request.env['gl.service.staff.member'].sudo().search([
            ('id', '=', member_id), ('pin_code', '=', pin_code), ('active', '=', True),
        ], limit=1)
        if member:
            request.session['gl_service_staff_member_id'] = member.id
            return request.redirect('/servicepersonal')
        request.session.pop('gl_service_staff_member_id', None)
        return request.render('gl_service_staff.portal_service_staff_response', {
            'success': False,
            'title': _('Link ungültig'),
            'message': _('Diese Mitarbeiter-Webseite konnte nicht geöffnet werden. Bitte den PIN-Code prüfen.'),
            'line': False,
        })

    @http.route(['/servicepersonal/logout'], type='http', auth='public', website=True, csrf=False)
    def service_staff_logout(self, **kw):
        request.session.pop('gl_service_staff_member_id', None)
        return request.redirect('/servicepersonal')

    @http.route(
        ['/servicepersonal/antwort/<int:line_id>/<string:token>/<string:answer>'],
        type='http', auth='public', website=True, csrf=False
    )
    def service_staff_response(self, line_id, token, answer, **kw):
        line = request.env['gl.service.shift.line'].sudo().search([
            ('id', '=', line_id), ('token', '=', token)
        ], limit=1)
        if not line:
            return request.render('gl_service_staff.portal_service_staff_response', {
                'success': False,
                'title': _('Link ungültig'),
                'message': _('Dieser Antwort-Link ist ungültig oder nicht mehr vorhanden.'),
                'line': False,
            })

        is_time_change_response = (
            line.time_change_state == 'pending'
        )
        if answer == 'accept':
            fully_staffed = (
                line.state != 'accepted'
                and line.shift_id.required_count > 0
                and line.shift_id.accepted_count >= line.shift_id.required_count
            )
            if fully_staffed:
                title = _('Schicht bereits besetzt')
                message = _('Vielen Dank! Für diese Schicht ist der Personalbedarf inzwischen gedeckt.')
            else:
                line._accept(source='public')
            if fully_staffed:
                pass
            elif is_time_change_response:
                title = _('Zeitänderung bestätigt')
                message = _('Danke! Die geänderte Arbeitszeit ist bestätigt.')
            elif line.state == 'accepted':
                title = _('Bereits gebucht')
                message = _('Du bist für diesen Einsatz bereits fest gebucht.')
            else:
                title = _('Verfügbarkeit gespeichert')
                message = _(
                    'Vielen Dank! Du bist als verfügbar vorgemerkt. '
                    'Eine feste Buchung erhältst du separat per E-Mail.'
                )
            success = True
        elif answer == 'decline':
            line._decline(source='public')
            if is_time_change_response:
                title = _('Rückmeldung gespeichert')
                message = _('Danke. Die geänderte Arbeitszeit wurde als nicht passend gemeldet.')
            elif line.state == 'accepted':
                title = _('Bereits gebucht')
                message = _(
                    'Du bist für diesen Einsatz bereits fest gebucht. '
                    'Bitte melde dich bei Änderungen direkt beim Groundlift-Team.'
                )
            else:
                title = _('Rückmeldung gespeichert')
                message = _('Danke! Du bist für diesen Einsatz als nicht verfügbar eingetragen.')
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

    @http.route(
        ['/servicepersonal/monatsmail/<int:member_id>/<string:token>/abbestellen'],
        type='http', auth='public', website=True, csrf=False
    )
    def service_staff_monthly_unsubscribe(self, member_id, token, **kw):
        member = request.env['gl.service.staff.member'].sudo().search([
            ('id', '=', member_id),
            ('monthly_unsubscribe_token', '=', token),
        ], limit=1)
        if not member:
            return request.render('gl_service_staff.portal_service_staff_response', {
                'success': False,
                'title': _('Link ungültig'),
                'message': _('Dieser Abmelde-Link ist ungültig.'),
                'line': False,
            })
        member.sudo().monthly_summary_opt_in = False
        return request.render('gl_service_staff.portal_service_staff_response', {
            'success': True,
            'title': _('Monatsmail abbestellt'),
            'message': _(
                'Du erhältst künftig keine monatliche Einsatzübersicht mehr. '
                'Einzelne Verfügbarkeitsanfragen und Buchungsbestätigungen bleiben davon unberührt.'
            ),
            'line': False,
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
