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
    frontend: same route, decisions made server-side per printer record.

    Lookup prefers the ``printer_id`` payload field (pos.printer record id),
    falling back to ``printer_ip`` for back-compat with cached browser
    sessions that predate this change.
    """

    @http.route('/pos-escpos/print', type='json', auth='user', methods=['POST'])
    def relay_print(self, action, printer_id=None, printer_ip=None, receipt=None):
        """Print a receipt or kick the cash drawer.

        :param action: 'print_receipt' or 'cashbox'
        :param printer_id: pos.printer record id (preferred lookup key)
        :param printer_ip: Target printer IP — used as a fallback lookup key
            and as the TCP target when the record has no IP or no matching
            record is found (legacy cached-session support).
        :param receipt: Base64-encoded JPEG image (only for 'print_receipt')
        :returns: dict with 'success' boolean and optional 'error' message
        """
        printer = self._find_printer(printer_id=printer_id, printer_ip=printer_ip)

        if action == 'print_receipt':
            if printer and printer.escpos_proxy_url:
                return printer._send_via_relay(receipt)
            # Local TCP path: prefer the record's configured IP, fall back to
            # whatever the frontend passed in.
            ip = (printer.escpos_printer_ip if printer else '') or printer_ip
            if not ip:
                return {
                    'success': False,
                    'error': 'No printer IP available for local TCP print.',
                }
            pw = int(printer.escpos_paper_width or '80') if printer else 80
            _logger.info("[escpos] local TCP -> %s (paper=%dmm)", ip, pw)
            return print_image(
                ip,
                DEFAULT_PRINTER_PORT,
                receipt,
                paper_width=pw,
                timeout=PRINTER_TIMEOUT,
            )

        if action == 'cashbox':
            # Cashbox pulses are local-only — the add-on has no /cashbox
            # endpoint. If a relay-configured printer is asked to kick the
            # drawer, the TCP path can't reach it from the cloud either, so
            # return a structured error early rather than time out.
            if printer and printer.escpos_proxy_url:
                return {
                    'success': False,
                    'error': 'Cashbox is not supported over the cloud relay.',
                }
            ip = (printer.escpos_printer_ip if printer else '') or printer_ip
            if not ip:
                return {
                    'success': False,
                    'error': 'No printer IP available for cashbox.',
                }
            return open_cashbox(
                ip,
                port=DEFAULT_PRINTER_PORT,
                timeout=PRINTER_TIMEOUT,
            )

        return {'success': False, 'error': f'Unknown action: {action}'}

    @staticmethod
    def _find_printer(printer_id=None, printer_ip=None):
        """Look up the pos.printer record.

        Prefers ``printer_id`` (stable identifier — works even when the
        record's IP is empty in cloud-relay mode). Falls back to
        ``printer_ip`` for back-compat with POS browser sessions that
        were loaded before this change.

        Returns an empty recordset if nothing matches. Uses sudo()
        because portal / self-order flows may drive prints from users
        that don't have direct read access to pos.printer.
        """
        Printer = request.env['pos.printer'].sudo()
        if printer_id:
            try:
                return Printer.browse(int(printer_id)).exists()
            except (ValueError, TypeError):
                pass
        if printer_ip:
            return Printer.search(
                [('escpos_printer_ip', '=', printer_ip)], limit=1,
            )
        return Printer
