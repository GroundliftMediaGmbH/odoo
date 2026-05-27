# -*- coding: utf-8 -*-
import json
from hmac import compare_digest

from odoo import fields, http
from odoo.http import Response, request


class EventGuestlistController(http.Controller):

    def _get_event_by_token(self, event_id, token):
        event = request.env['event.event'].sudo().browse(event_id).exists()
        if not event or not event.guestlist_access_token:
            return request.env['event.event'].sudo()
        if not compare_digest(str(event.guestlist_access_token), str(token or '')):
            return request.env['event.event'].sudo()
        return event

    @http.route('/event/guestlist/<int:event_id>/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def guestlist_page(self, event_id, token, **kwargs):
        event = self._get_event_by_token(event_id, token)
        if not event:
            return request.not_found()
        lines = event.guestlist_line_ids.sudo().filtered('active').sorted(lambda line: (line.checked_in, (line.name or '').lower(), line.id))
        return request.render('gl_event_guestlist.public_guestlist_page', {
            'event': event,
            'guestlist_lines': lines,
            'token': token,
            'total_qty': sum(lines.mapped('quantity_int')),
            'checked_qty': sum(lines.filtered('checked_in').mapped('quantity_int')),
        })

    @http.route('/event/guestlist/check/<int:line_id>/<string:token>', type='http', auth='public', methods=['POST'], csrf=False, sitemap=False)
    def guestlist_toggle(self, line_id, token, **kwargs):
        line = request.env['gl.event.guestlist.line'].sudo().browse(line_id).exists()
        if not line or not line.event_id.guestlist_access_token or not compare_digest(str(line.event_id.guestlist_access_token), str(token or '')):
            return Response(
                json.dumps({'ok': False, 'error': 'forbidden'}),
                status=403,
                content_type='application/json; charset=utf-8',
            )

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except Exception:
            payload = {}

        checked = bool(payload.get('checked'))
        public_user = request.env.ref('base.public_user', raise_if_not_found=False)
        checked_by_user_id = False
        if checked and (not public_user or request.env.user.id != public_user.id):
            checked_by_user_id = request.env.user.id

        line.write({
            'checked_in': checked,
            'checked_in_datetime': fields.Datetime.now() if checked else False,
            'checked_by_user_id': checked_by_user_id,
        })

        event = line.event_id
        active_lines = event.guestlist_line_ids.sudo().filtered('active')
        response = {
            'ok': True,
            'line_id': line.id,
            'checked': line.checked_in,
            'checked_qty': sum(active_lines.filtered('checked_in').mapped('quantity_int')),
            'total_qty': sum(active_lines.mapped('quantity_int')),
        }
        return Response(json.dumps(response), content_type='application/json; charset=utf-8')
