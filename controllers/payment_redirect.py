# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import re
import logging

_logger = logging.getLogger(__name__)


class PaymentRedirectController(http.Controller):
    """
    Controller to handle redirects from payment confirmation page
    back to POS Self Order with proper access token.
    """

    @http.route('/pos-self-order/return-to-order', type='http', auth='public', website=True)
    def return_to_order(self, reference=None, **kwargs):
        """
        Redirect to POS Self Order page with access token.
        Extracts config_id from order reference and builds proper URL.

        Reference format: "Self-Order SSSSS-CCC-NNNN"
        where SSSSS=session_id, CCC=config_id, NNNN=sequence.
        """
        pos_config = None
        company = request.env.company

        # Try to find config from reference
        if reference:
            match = re.search(r'(\d+)-(\d+)-(\d+)', reference)
            if match:
                config_num = int(match.group(2))
                # Use config_num to find the specific POS config
                pos_config = request.env['pos.config'].sudo().search([
                    ('id', '=', config_num),
                    ('self_ordering_mode', 'in', ['mobile', 'kiosk']),
                    ('company_id', '=', company.id),
                ], limit=1)

        # Fallback: find any self-ordering config for this company
        if not pos_config:
            pos_config = request.env['pos.config'].sudo().search([
                ('self_ordering_mode', 'in', ['mobile', 'kiosk']),
                ('company_id', '=', company.id),
            ], limit=1)

        if not pos_config:
            _logger.warning(
                "No self-ordering POS config found for payment redirect (reference=%s)",
                reference,
            )
            return request.not_found()

        # Build redirect URL
        access_token = pos_config.access_token
        if access_token:
            redirect_url = f'/pos-self/{pos_config.id}?access_token={access_token}'
        else:
            redirect_url = f'/pos-self/{pos_config.id}/products'

        return request.redirect(redirect_url)
