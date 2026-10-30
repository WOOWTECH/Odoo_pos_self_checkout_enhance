# -*- coding: utf-8 -*-
from odoo.http import request
from odoo.addons.pos_online_payment_self_order.controllers.payment_portal import PaymentPortalSelfOrder


class PaymentPortalSelfOrderEnh(PaymentPortalSelfOrder):
    """Suppress payment notifications for payment-gated orders.

    Two suppression rules:
    1. 'progress'/'fail' for pending_online orders — prevents leaking order
       to POS before customer pays.
    2. 'success' for already-paid orders — _process_saved_order() already
       sent notifications + AUTO_FIRE_PRINT; a second notify_synchronisation
       from pos_order_pay_confirmation would cause duplicate kitchen prints.
    """

    def _send_notification_payment_status(self, pos_order_id, status):
        pos_order = request.env['pos.order'].sudo().browse(pos_order_id)
        # Suppress progress/fail for pending orders
        if pos_order.self_order_payment_status == 'pending_online' and status != 'success':
            return
        # Suppress duplicate success notification — _process_saved_order
        # already handled notifications and kitchen printing
        if pos_order.self_order_payment_status == 'paid' and status == 'success':
            return
        return super()._send_notification_payment_status(pos_order_id, status)
