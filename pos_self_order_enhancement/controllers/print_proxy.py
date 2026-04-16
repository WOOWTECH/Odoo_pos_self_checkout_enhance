# -*- coding: utf-8 -*-
import logging

import requests

from odoo import http
from odoo.http import request

from ..vendor.escpos_min import print_image, open_cashbox

_logger = logging.getLogger(__name__)

# Default ESC/POS network printer port
DEFAULT_PRINTER_PORT = 9100
# Socket timeout (seconds). Short on purpose: an offline printer must not
# stall an Odoo HTTP worker.
PRINTER_TIMEOUT = 3
# Relay HTTP timeout (seconds). Longer than the TCP timeout because the
# request traverses Internet + tunnel + LAN before the printer even sees it.
RELAY_TIMEOUT = 10


class PosEscPosProxy(http.Controller):
    """In-process ESC/POS print controller.

    Receives a base64-encoded JPEG receipt from the POS browser and prints
    it either:
      - directly via a TCP socket to the printer at port 9100 (default), or
      - through an HTTP proxy (cloud relay mode) when the target pos.printer
        record has `escpos_proxy_url` set.

    Routing is invisible to the POS frontend: same route, same payload, same
    response shape. The decision is made server-side per printer.
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
                return self._dispatch_via_relay(printer, receipt)
            return self._dispatch_via_tcp(printer_ip, receipt)

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

    # ── dispatch helpers ──────────────────────────────────────────

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

    @staticmethod
    def _dispatch_via_tcp(printer_ip, image_b64):
        _logger.info("[escpos] local TCP -> %s", printer_ip)
        return print_image(
            printer_ip,
            DEFAULT_PRINTER_PORT,
            image_b64,
            paper_width=80,
            timeout=PRINTER_TIMEOUT,
        )

    @staticmethod
    def _dispatch_via_relay(printer, image_b64):
        """POST the print job to the printer's configured cloud relay.

        Returns {'success': bool, 'error': str|None} — same envelope shape as
        the TCP path so the POS frontend treats both identically.
        """
        url = (printer.escpos_proxy_url or '').rstrip('/') + '/print'
        api_key = printer.escpos_proxy_api_key or ''
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        payload = {
            'image_base64': image_b64,
            'printer_ip': printer.escpos_printer_ip,
            'cut': True,
            'beep': False,
        }
        _logger.info(
            "[escpos] relay -> %s (printer=%s)",
            url, printer.escpos_printer_ip,
        )
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=RELAY_TIMEOUT,
            )
        except requests.RequestException as e:
            _logger.warning("[escpos] relay request failed: %s", e)
            return {'success': False, 'error': f'Relay unreachable: {e}'}

        # Relay responds with {ok: bool, error?: str}. Map to our
        # {success, error} envelope that the frontend already handles.
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code == 200 and body.get('ok'):
            return {'success': True, 'error': None}
        err = body.get('error') or f'relay returned HTTP {resp.status_code}'
        _logger.warning("[escpos] relay refused: %s", err)
        return {'success': False, 'error': err}
