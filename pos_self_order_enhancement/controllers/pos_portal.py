"""Portal-user access to the POS cashier UI.

Adds three pieces:

1. Override of ``PosController.pos_web`` (``/pos/ui`` / ``/pos/web``) so
   portal users whose partner has any entry in ``portal_pos_config_ids``
   can load the POS cashier interface. The target shop is picked via
   ``?config_id=N``; if the user has exactly one assigned shop, that
   config is used implicitly.  Internal users continue to use the stock
   Odoo behaviour.

2. New ``/my/pos`` route that renders the shop picker when the user has
   multiple shops assigned, and auto-redirects when there is only one.

3. Extension of ``CustomerPortal._prepare_home_portal_values`` so the
   "My Account" portal home page can render a "Point of Sale" card
   whose subtitle reflects how many shops the user has access to.
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
        # ir.http._authenticate may have already swapped request.env to a
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
        configs = partner.portal_pos_config_ids.filtered('active')
        if not configs:
            return request.not_found()

        # Resolve which config this request targets.
        if config_id:
            try:
                requested_id = int(config_id)
            except (TypeError, ValueError):
                return request.not_found()
            target = configs.filtered(lambda c: c.id == requested_id)
            if not target:
                # Config is either unknown or not assigned to this partner.
                return request.not_found()
        elif len(configs) == 1:
            target = configs
        else:
            # Ambiguous — send user to the picker.
            return request.redirect('/my/pos')

        proxy_user = target.self_ordering_default_user_id
        if not proxy_user or not proxy_user.active:
            _logger.warning(
                "Portal POS: pos.config %s has no active "
                "self_ordering_default_user_id; portal user %s cannot "
                "access the POS UI.",
                target.id, session_user.login,
            )
            return request.not_found()

        # Pin the active shop to the HTTP session so subsequent RPCs
        # (/web/dataset/call_kw, /longpolling/, etc.) can resolve which
        # proxy user to elevate to.
        request.session['portal_pos_active_config_id'] = target.id

        # Elevate request.env for this controller as well (ir.http has
        # already done it for requests AFTER the session key is set, but
        # on the very first /pos/ui hit the session key is only being set
        # now, so we must elevate explicitly here).
        request.update_env(user=proxy_user.id)

        company = target.company_id
        pos_config = request.env['pos.config'].browse(target.id).with_company(company)

        domain = [
            ('state', 'in', ['opening_control', 'opened']),
            ('rescue', '=', False),
            ('config_id', '=', target.id),
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

    @http.route(['/my/pos'], type='http', auth='user', website=True)
    def portal_my_pos(self, **kw):
        user = request.env.user
        # Admin/internal users have the real backend; send them there.
        if user._is_internal():
            return request.redirect('/odoo/action-point_of_sale.action_client_pos_menu')
        if not user._is_portal():
            return request.redirect('/my')

        partner = user.sudo().partner_id
        configs = partner.portal_pos_config_ids.filtered('active')
        if not configs:
            return request.redirect('/my')
        if len(configs) == 1:
            return request.redirect('/pos/ui?config_id=%s' % configs.id)

        return request.render(
            'pos_self_order_enhancement.portal_pos_picker',
            {
                'page_name': 'portal_pos',
                'configs': configs,
            },
        )

    @http.route(['/my/kds'], type='http', auth='user', website=True)
    def portal_my_kds(self, **kw):
        user = request.env.user
        if user._is_internal():
            return request.redirect('/my')
        if not user._is_portal():
            return request.redirect('/my')

        partner = user.sudo().partner_id
        configs = partner.portal_pos_config_ids.filtered(
            lambda c: c.active and c.kds_enabled
        )
        if not configs:
            return request.redirect('/my')
        if len(configs) == 1:
            return request.redirect(
                '/pos-kds/%s?token=%s' % (configs.id, configs.kds_access_token)
            )

        return request.render(
            'pos_self_order_enhancement.portal_kds_picker',
            {
                'page_name': 'portal_kds',
                'configs': configs,
            },
        )

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.sudo().partner_id
        configs = partner.portal_pos_config_ids.filtered('active')
        values['portal_pos_config_count'] = len(configs)
        if len(configs) == 1:
            values['portal_pos_config_label'] = configs.name
        elif len(configs) > 1:
            values['portal_pos_config_label'] = '%d shops' % len(configs)
        else:
            values['portal_pos_config_label'] = ''

        kds_configs = configs.filtered('kds_enabled')
        values['portal_kds_config_count'] = len(kds_configs)
        if len(kds_configs) == 1:
            values['portal_kds_config_label'] = kds_configs.name
        elif len(kds_configs) > 1:
            values['portal_kds_config_label'] = '%d kitchens' % len(kds_configs)
        else:
            values['portal_kds_config_label'] = ''
        return values
