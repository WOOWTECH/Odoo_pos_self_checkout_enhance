# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

from ..vendor.escpos_min import print_image, open_cashbox

_logger = logging.getLogger(__name__)

# Default ESC/POS network printer port
DEFAULT_PRINTER_PORT = 9100
# Socket timeout (seconds). Short on purpose: an offline printer must not
# stall an Odoo HTTP worker.
PRINTER_TIMEOUT = 3


class PosEscPosProxy(http.Controller):
    """In-process ESC/POS print controller.

    Receives a base64-encoded JPEG receipt from the POS browser and prints
    it either:
      - directly via a TCP socket to the printer at port 9100 (default), or
      - through an HTTP proxy (cloud relay mode) when the target pos.printer
        record has `escpos_proxy_url` set.

    The relay path delegates to ``pos.printer._send_via_relay`` — see the
    model for the actual HTTP POST. Routing is invisible to the POS
    frontend: same route, same payload, same response shape. The decision
    is made server-side per printer.
    """

    @http.route('/pos-escpos/print', type='json', auth='user', methods=['POST'])
    def relay_print(self, printer_ip, action, receipt=None):
        """Print a receipt or kick the cash drawer.

        :param printer_ip: Target printer IP address (e.g., '192.168.2.241')
        :param action: 'print_receipt' or 'cashbox'
        :param receipt: Base64-encoded JPEG image (only for 'print_receipt')
        :returns: dict with 'success' boolean and optional 'error' message
        """
        if action == 'print_receipt':
            printer = self._find_printer(printer_ip)
            if printer and printer.escpos_proxy_url:
                return printer._send_via_relay(receipt)
            _logger.info("[escpos] local TCP -> %s", printer_ip)
            return print_image(
                printer_ip,
                DEFAULT_PRINTER_PORT,
                receipt,
                paper_width=80,
                timeout=PRINTER_TIMEOUT,
            )

        if action == 'cashbox':
            # Cashbox pulses are local-only — the add-on has no /cashbox
            # endpoint. If a relay-configured printer is asked to kick the
            # drawer, the TCP path can't reach it from the cloud either, so
            # return a structured error early rather than time out.
            printer = self._find_printer(printer_ip)
            if printer and printer.escpos_proxy_url:
                return {
                    'success': False,
                    'error': 'Cashbox is not supported over the cloud relay.',
                }
            return open_cashbox(
                printer_ip,
                port=DEFAULT_PRINTER_PORT,
                timeout=PRINTER_TIMEOUT,
            )

        return {'success': False, 'error': f'Unknown action: {action}'}

    @staticmethod
    def _find_printer(printer_ip):
        """Look up the pos.printer record by configured IP.

        Returns the first match, or an empty recordset if nothing matches.
        Uses sudo() because portal / self-order flows may drive prints from
        users that don't have direct read access to pos.printer.
        """
        if not printer_ip:
            return request.env['pos.printer']
        return request.env['pos.printer'].sudo().search(
            [('escpos_printer_ip', '=', printer_ip)], limit=1,
        )
