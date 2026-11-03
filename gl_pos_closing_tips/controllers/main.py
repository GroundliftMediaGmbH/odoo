from odoo import http
from odoo.http import request


class GroundliftClosingTips(http.Controller):
    @http.route('/gl_pos_closing_tips/summary', type='jsonrpc', auth='user', methods=['POST'])
    def closing_tips_summary(self, session_id=None, **kwargs):
        if not request.env.user.has_group('point_of_sale.group_pos_user') and not request.env.user.has_group('point_of_sale.group_pos_manager'):
            return {'error': 'access_denied'}
        try:
            session_id = int(session_id)
        except (TypeError, ValueError):
            return {'error': 'invalid_session'}
        session = request.env['pos.session'].search([('id', '=', session_id)], limit=1)
        if not session:
            return {'error': 'session_not_found'}
        orders = request.env['pos.order'].search([
            ('session_id', '=', session.id),
            ('state', 'in', ('paid', 'done', 'invoiced')),
        ])
        cash = card = mixed = total = 0.0
        for order in orders:
            # Odoo native tip values; do not count other products called "tip".
            amount = float(order.tip_amount or 0.0) if 'tip_amount' in order._fields else 0.0
            if not amount:
                product = session.config_id.tip_product_id if 'tip_product_id' in session.config_id._fields else False
                if product:
                    amount = sum(line.price_subtotal_incl for line in order.lines if line.product_id == product)
            if not amount:
                continue
            total += amount
            methods = order.payment_ids.mapped('payment_method_id')
            methods = methods.filtered(lambda method: method)
            if not methods:
                mixed += amount
            elif all(method.is_cash_count for method in methods):
                cash += amount
            elif all(not method.is_cash_count for method in methods):
                card += amount
            else:
                mixed += amount
        currency = session.currency_id or session.company_id.currency_id
        return {
            'total': currency.round(total),
            'cash': currency.round(cash),
            'noncash': currency.round(card),
            'mixed': currency.round(mixed),
            'currency': currency.symbol,
            'currency_position': currency.position,
            'session_id': session.id,
        }
