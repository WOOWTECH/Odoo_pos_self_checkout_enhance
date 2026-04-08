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
    it directly via a TCP socket to the printer at port 9100. No external
    process, no python-escpos, no Flask.

    Same route + payload contract as the legacy `localhost:8073` proxy
    relay, so the POS frontend (`escpos_network_printer.js`) needs no
    changes — this is a drop-in replacement.
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
            return print_image(
                printer_ip,
                DEFAULT_PRINTER_PORT,
                receipt,
                paper_width=80,
                timeout=PRINTER_TIMEOUT,
            )
        elif action == 'cashbox':
            return open_cashbox(
                printer_ip,
                port=DEFAULT_PRINTER_PORT,
                timeout=PRINTER_TIMEOUT,
            )
        else:
            return {'success': False, 'error': f'Unknown action: {action}'}
