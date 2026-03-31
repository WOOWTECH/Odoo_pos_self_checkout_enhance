# -*- coding: utf-8 -*-
import json
import logging

import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

PRINT_PROXY_URL = 'http://localhost:8073'


class PosEscPosProxy(http.Controller):
    """Relay controller that forwards print jobs from the POS browser
    to the local ESC/POS print proxy server.

    This avoids CORS/mixed-content issues since the POS browser
    communicates with Odoo (same-origin HTTPS), and Odoo forwards
    the request to the print proxy (server-to-server HTTP).
    """

    @http.route('/pos-escpos/print', type='json', auth='user', methods=['POST'])
    def relay_print(self, printer_ip, action, receipt=None):
        """Relay a print job to the ESC/POS print proxy.

        :param printer_ip: Target printer IP address (e.g., '192.168.1.100')
        :param action: 'print_receipt' or 'cashbox'
        :param receipt: Base64-encoded JPEG image (for print_receipt action)
        :returns: dict with 'success' boolean and optional 'error' message
        """
        payload = {
            'params': {
                'data': {
                    'action': action,
                    'receipt': receipt or '',
                    'printer_ip': printer_ip,
                }
            }
        }

        try:
            resp = requests.post(
                f'{PRINT_PROXY_URL}/hw_proxy/default_printer_action',
                json=payload,
                timeout=15,
            )
            result = resp.json()
            return {'success': result.get('result', False)}
        except requests.ConnectionError:
            _logger.warning(
                'ESC/POS print proxy not reachable at %s', PRINT_PROXY_URL
            )
            return {
                'success': False,
                'error': 'Print proxy server is not running. '
                         'Start it with: python tools/print_proxy.py',
            }
        except Exception as e:
            _logger.exception('ESC/POS print relay failed')
            return {'success': False, 'error': str(e)}
