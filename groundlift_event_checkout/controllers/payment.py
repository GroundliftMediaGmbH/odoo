# -*- coding: utf-8 -*-
"""Server-side ticket registration protection for Odoo 19 website payments.

Registrations must exist while the order is still a draft. The original
/groundlift/checkout/customer JSON-RPC continues to populate customer details;
this fallback protects payment paths that bypass that browser callback.
"""
import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
from odoo.addons.website_sale.controllers.payment import PaymentPortal

_logger = logging.getLogger(__name__)


class GroundliftPaymentPortal(PaymentPortal):
    @http.route()
    def shop_payment_transaction(self, order_id, access_token, **kwargs):
        # Preserve Odoo's standard cart/access/payment checks and locking.
        return super().shop_payment_transaction(order_id, access_token, **kwargs)

    def _validate_transaction_for_order(self, transaction, sale_order):
        result = super()._validate_transaction_for_order(transaction, sale_order)
        order = sale_order.sudo()

        # All website event-ticket payments on the enabled Groundlift website,
        # including legacy Odoo checkout and sessions without the JS callback.
        # Excludes backend confirmations, POS, free carts and paid/cancelled SOs.
        if (order.state != 'draft' or not order.website_id
                or not order.website_id.groundlift_event_checkout_enabled
                or order.amount_total <= 0):
            return result

        lines = order.order_line.filtered(
            lambda line: not line.display_type and line.event_ticket_id
            and line.service_tracking == 'event'
        )
        if not lines:
            return result

        needed = sum(max(0, int(line.product_uom_qty)) for line in lines)
        existing = sum(len(line.registration_ids.filtered(lambda reg: reg.state != 'cancel'))
                       for line in lines)
        if existing >= needed:
            return result

        # Native Odoo method only adds missing registrations. It is safe to
        # call before payment, but not after the order has been confirmed.
        # Raising here rolls back transaction creation rather than taking
        # payment when tickets cannot be prepared.
        lines._init_registrations()
        current = sum(len(line.registration_ids.filtered(lambda reg: reg.state != 'cancel'))
                      for line in lines)
        if current < needed:
            raise ValidationError(
                'Ticket registrations could not be prepared before payment. '
                'Please retry checkout or contact Groundlift.'
            )

        _logger.warning(
            'Groundlift pre-payment registration fallback: order=%s tx=%s '
            'created=%s customer_rpc_marker=%s checkout_session_marker=%s',
            order.name, transaction.reference, current - existing,
            bool(order.meta_first_name) if 'meta_first_name' in order._fields else False,
            request.session.get('gl_event_checkout_order_id') == order.id,
        )
        return result
