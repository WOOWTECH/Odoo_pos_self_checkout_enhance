# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import re


class PaymentRedirectController(http.Controller):
    """
    Controller to handle redirects from payment confirmation page
    back to POS Self Order with proper access token
    """

    @http.route('/pos-self-order/return-to-order', type='http', auth='public', website=True)
    def return_to_order(self, reference=None, **kwargs):
        """
        Redirect to POS Self Order page with access token.
        Extracts config_id from order reference and builds proper URL.

        Reference format: "Self-Order XXXXX-YYY-ZZZZ" where XXXXX is config related
        """
        # Default config_id
        config_id = 1
        access_token = None

        # Try to find config from reference
        if reference:
            # Reference format: "Self-Order 00003-001-0048-3"
            # The first number group might be related to config
            match = re.search(r'(\d+)-(\d+)-(\d+)', reference)
            if match:
                # Try to find the POS config
                config_num = int(match.group(1))
                pos_config = request.env['pos.config'].sudo().search([
                    ('self_ordering_mode', 'in', ['mobile', 'kiosk']),
                ], limit=1)
                if pos_config:
                    config_id = pos_config.id
                    access_token = pos_config.access_token

        # If no reference, try to get from session or find default config
        if not access_token:
            pos_config = request.env['pos.config'].sudo().search([
                ('self_ordering_mode', 'in', ['mobile', 'kiosk']),
            ], limit=1)
            if pos_config:
                config_id = pos_config.id
                access_token = pos_config.access_token

        # Build redirect URL
        if access_token:
            redirect_url = f'/pos-self/{config_id}?access_token={access_token}'
        else:
            redirect_url = f'/pos-self/{config_id}/products'

        return request.redirect(redirect_url)
