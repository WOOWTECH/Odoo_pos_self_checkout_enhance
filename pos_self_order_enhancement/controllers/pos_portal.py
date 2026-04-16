"""Portal-user access to the POS cashier UI.

Adds two pieces:

1. Override of ``PosController.pos_web`` (``/pos/ui`` / ``/pos/web``) so
   portal users with an assigned ``portal_pos_config_id`` on their partner
   can load the POS cashier interface. Internal users continue to use the
   stock Odoo behaviour.

2. Extension of ``CustomerPortal._prepare_home_portal_values`` so the
   "My Account" portal home page can render a "Point of Sale" card.
"""

import logging

from odoo import http
from odoo.http import request

from odoo.addons.point_of_sale.controllers.main import PosController
from odoo.addons.portal.controllers.portal import CustomerPortal

_logger = logging.getLogger(__name__)


class PosPortalController(PosController):

    @http.route(['/pos/web', '/pos/ui'], type='http', auth='user')
    def pos_web(self, config_id=False, from_backend=False, **k):
        # ir.http._authenticate may have already swapped request.env to the
        # proxy user. We therefore look up the *session's* user (the actual
        # logged-in identity) to decide which flow to run.
        session_uid = request.session.uid
        session_user = request.env['res.users'].sudo().browse(session_uid)

        if session_user._is_internal():
            return super().pos_web(
                config_id=config_id, from_backend=from_backend, **k
            )

        if not session_user._is_portal():
            return request.not_found()

        partner = session_user.partner_id
        pos_config_sudo = partner.portal_pos_config_id
        if not pos_config_sudo or not pos_config_sudo.active:
            return request.not_found()

        proxy_user = pos_config_sudo.self_ordering_default_user_id
        if not proxy_user or not proxy_user.active:
            _logger.warning(
                "Portal POS: pos.config %s has no active "
                "self_ordering_default_user_id; portal user %s cannot "
                "access the POS UI.",
                pos_config_sudo.id, session_user.login,
            )
            return request.not_found()

        # ir.http._authenticate has already swapped request.env to the
        # proxy user for this request, but to be defensive we elevate
        # explicitly here as well -- this controller is the entry point.
        request.update_env(user=proxy_user.id)

        # Force the config to the one assigned on the partner. Ignore any
        # ?config_id=... coming from the URL so portal users can never
        # pivot to another config.
        config_id = pos_config_sudo.id
        company = pos_config_sudo.company_id
        pos_config = request.env['pos.config'].browse(config_id).with_company(company)

        domain = [
            ('state', 'in', ['opening_control', 'opened']),
            ('rescue', '=', False),
            ('config_id', '=', config_id),
        ]
        pos_session = request.env['pos.session'].sudo().search(domain, limit=1)

        if not pos_config or not pos_config.active:
            return request.not_found()

        if not pos_config.has_active_session:
            pos_config.open_ui()
            pos_session = request.env['pos.session'].sudo().search(domain, limit=1)

        if not pos_session:
            return request.not_found()

        session_info = pos_session._update_session_info(
            request.env['ir.http'].session_info()
        )
        # Expose a flag to the POS frontend so we can redirect the
        # "close POS" button to /my instead of the backend action.
        session_info['portal_pos_mode'] = True

        use_lna = bool(pos_session.env['ir.config_parameter'].get_param(
            'point_of_sale.use_lna'
        ))
        context = {
            'from_backend': 0,
            'use_pos_fake_tours': False,
            'session_info': session_info,
            'login_number': pos_session.with_company(company).login(),
            'pos_session_id': pos_session.id,
            'pos_config_id': pos_session.config_id.id,
            'access_token': pos_session.config_id.access_token,
            'use_lna': use_lna,
        }
        response = request.render('point_of_sale.index', context)
        response.headers['Cache-Control'] = 'no-store'
        return response


class PortalHomePosCard(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.sudo().partner_id
        pos_config = partner.portal_pos_config_id
        if pos_config and pos_config.active:
            values['portal_pos_config_name'] = pos_config.name
            values['portal_pos_config_id'] = pos_config.id
        return values
