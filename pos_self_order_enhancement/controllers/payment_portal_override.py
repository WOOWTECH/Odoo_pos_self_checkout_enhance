# -*- coding: utf-8 -*-
from odoo.http import request
from odoo.addons.pos_online_payment_self_order.controllers.payment_portal import PaymentPortalSelfOrder


class PaymentPortalSelfOrderEnh(PaymentPortalSelfOrder):
    """Suppress online payment 'progress' notifications for payment-gated orders.

    The base pos_online_payment_self_order module sends a 'progress' notification
    (including notify_synchronisation) as soon as the /pos/pay/ page loads — before
    the customer has actually paid.  For pay-per-order mode this leaks the order
    to POS prematurely.  We suppress 'progress' and 'fail' for pending_online
    orders and only let 'success' through.
    """

    def _send_notification_payment_status(self, pos_order_id, status):
        pos_order = request.env['pos.order'].sudo().browse(pos_order_id)
        if pos_order.self_order_payment_status == 'pending_online' and status != 'success':
            return
        return super()._send_notification_payment_status(pos_order_id, status)
