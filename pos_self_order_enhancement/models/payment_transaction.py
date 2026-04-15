# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _handle_notification_data(self, provider_code, notification_data):
        """Eagerly post-process POS online payment transactions.

        Redirect-based payment providers (ECPay, etc.) send a server-to-server
        callback that calls _handle_notification_data() but never reaches the
        standard /pos/pay/confirmation/ endpoint where _process_pos_online_payment()
        would normally be called.  Without this override, POS order processing
        relies on the _cron_post_process() cron job which runs with variable delay.

        We call _post_process() immediately for POS order transactions so the
        payment is added to the pos.order and _process_saved_order() fires POS
        notifications without delay.
        """
        tx = super()._handle_notification_data(provider_code, notification_data)
        if (
            tx
            and tx.pos_order_id
            and tx.state in ('authorized', 'done')
            and not tx.is_post_processed
        ):
            _logger.info(
                "POS online payment: eagerly post-processing tx %s for order %s",
                tx.reference,
                tx.pos_order_id.pos_reference,
            )
            tx._post_process()
        return tx
