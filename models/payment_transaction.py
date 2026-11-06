# -*- coding: utf-8 -*-
import logging

from odoo import api, models, tools

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_pos_self_return_token(self):
        """Token proving that the caller saw this transaction's confirmation.

        Embedded in the "Return to Ordering" link of the payment
        confirmation page (only reachable with the transaction's own access
        token) and checked by /pos-self-order/return-to-order.
        """
        self.ensure_one()
        return tools.hmac(self.env(su=True), 'pos_self_order_enhancement-return-to-order', self.id)

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

            # Auto-issue Taiwan e-invoice after payment is confirmed
            tx._auto_issue_einvoice()

        return tx

    def _auto_issue_einvoice(self):
        """Issue Taiwan e-invoice automatically after POS online payment.

        Uses the carrier preferences saved by the customer on the self-order
        payment page.  Non-blocking: payment succeeds regardless of outcome.
        """
        order = self.pos_order_id
        if not order or not order.config_id.ecpay_einvoice_enabled:
            return
        if not order.config_id.is_ecpay_installed:
            return
        if order.ecpay_invoice_id or order.tw_invoice_status == 'issued':
            return

        carrier_data = {
            'carrier_type': order.tw_carrier_type or 'print',
            'carrier_num': order.tw_carrier_num or '',
            'love_code': order.tw_love_code or '',
            'buyer_tax_id': order.tw_buyer_tax_id or '',
            'buyer_name': order.tw_buyer_name or '',
        }
        try:
            result = order.action_issue_einvoice(carrier_data)
            if result.get('success'):
                _logger.info(
                    "Auto-issued e-invoice %s for POS order %s",
                    result.get('invoice_no'), order.pos_reference,
                )
                # Notify POS to print if carrier type requires paper
                if order.tw_carrier_type in ('print', 'b2b'):
                    for config in order.config_id:
                        config._notify('EINVOICE_PRINT', {
                            'order_id': order.id,
                        })
            else:
                _logger.warning(
                    "E-invoice auto-issuance failed for order %s: %s",
                    order.pos_reference, result.get('error'),
                )
        except Exception as e:
            _logger.error(
                "E-invoice auto-issuance exception for order %s: %s",
                order.pos_reference, e,
            )
