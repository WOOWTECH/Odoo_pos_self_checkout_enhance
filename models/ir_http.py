"""Per-request user context swap for portal users accessing the POS UI.

When a portal user has a ``portal_pos_config_ids`` assignment on their
partner and they make a request to a POS-related path, the request
environment is transparently elevated to the currently-active config's
``self_ordering_default_user_id`` (an internal user with POS permissions).

The "currently-active" config is pinned on the HTTP session under
``portal_pos_active_config_id`` by the ``/pos/ui`` controller. This
lets subsequent RPCs (/web/dataset/call_kw, /longpolling/, /websocket)
resolve which proxy user to use, since those requests don't carry
``config_id`` in the body.

The HTTP session cookie is NOT mutated — only ``request.env`` is updated
for the duration of the current request. This means:

- Navigating to any non-POS path (e.g. ``/my``, ``/odoo``) still
  identifies the user as the portal user.
- The portal user cannot escalate to backend access via URL manipulation.
- Security is enforced by the proxy user's own ACLs and record rules.
"""

from odoo import models
from odoo.http import request

# Paths where the portal -> proxy swap is allowed. A request to any other
# path keeps the portal user's identity intact.
_POS_SWAP_EXACT_PATHS = frozenset({
    '/pos/ui',
    '/pos/web',
})

_POS_SWAP_PREFIXES = (
    '/pos/',                # POS page + our own /pos-self-order/, /pos-kds/...
    '/pos-self/',           # self-order pages
    '/pos-self-order/',     # self-order controller endpoints
    '/pos-kds/',            # kitchen display
    '/web/webclient/',      # load_menus, translations, qweb, version_info
    '/web/image/',          # product images used inside the POS UI
    '/web/content/',        # static content (attachments referenced by POS)
    '/web/static/',         # static assets
    '/longpolling/',        # bus notifications
    '/websocket',           # bus websocket
)

# Narrower set: /web/dataset/ and /report/ require extra validation
# because they handle arbitrary model RPC calls.
_POS_SWAP_RPC_PREFIXES = (
    '/web/dataset/',    # call_kw, call_button, resequence
    '/report/',         # receipt/report rendering
)

# Models that the portal POS proxy user is allowed to access via RPC.
_POS_ALLOWED_MODELS = frozenset({
    'pos.order', 'pos.order.line', 'pos.session', 'pos.config',
    'pos.payment', 'pos.payment.method', 'pos.category',
    'product.product', 'product.template', 'product.pricelist',
    'product.pricelist.item', 'account.tax', 'account.tax.group',
    'res.currency', 'res.company', 'res.country', 'res.lang',
    'restaurant.table', 'restaurant.floor',
    'stock.picking.type', 'decimal.precision',
    'pos.printer', 'pos.combo', 'pos.combo.line',
    'ir.ui.view', 'ir.attachment',
})


def _path_allows_swap(path):
    if path in _POS_SWAP_EXACT_PATHS:
        return True
    if any(path.startswith(p) for p in _POS_SWAP_PREFIXES):
        return True
    # For broad RPC prefixes, allow swap but the caller must also
    # validate the target model (see _pos_portal_swap_user).
    if any(path.startswith(p) for p in _POS_SWAP_RPC_PREFIXES):
        return True
    return False


def _is_pos_rpc_path(path):
    """Return True if the path hits a broad RPC prefix that needs model validation."""
    return any(path.startswith(p) for p in _POS_SWAP_RPC_PREFIXES)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_translation_frontend_modules_name(cls):
        mods = super()._get_translation_frontend_modules_name()
        return mods + ['pos_self_order_enhancement']

    @classmethod
    def _authenticate(cls, endpoint):
        super()._authenticate(endpoint)
        cls._pos_portal_swap_user()

    @classmethod
    def _pos_portal_swap_user(cls):
        """Swap request.env to the proxy user when a portal user with an
        active POS session is hitting a POS-related path."""
        env = request.env
        if not env or not env.uid:
            return

        # Only portal users are subject to the swap.
        user = env.user
        if not user._is_portal():
            return

        path = request.httprequest.path
        if not _path_allows_swap(path):
            return

        # For broad RPC paths (/web/dataset/, /report/), validate that
        # the target model is POS-related to prevent privilege escalation
        # to non-POS models.
        if _is_pos_rpc_path(path):
            try:
                data = request.get_json_data() or {}
                params = data.get('params', {})
                model = params.get('model', '') or params.get('args', [''])[0] if isinstance(params.get('args'), list) else ''
                if model and model not in _POS_ALLOWED_MODELS:
                    return
            except Exception:
                pass  # If we can't parse, let the normal auth handle it

        active_id = request.session.get('portal_pos_active_config_id')
        if not active_id:
            # No shop currently pinned (user is e.g. browsing /my/pos
            # before picking a shop). Let the portal user's own identity
            # handle the request -- if it's a real POS RPC they'll get
            # an AccessError, which is the correct behaviour.
            return

        partner = user.sudo().partner_id
        pos_config = partner.portal_pos_config_ids.filtered(
            lambda c: c.id == active_id and c.active
        )
        if not pos_config:
            # Config was unassigned or archived since it was pinned.
            # Drop the stale key so we don't keep re-validating it.
            request.session.pop('portal_pos_active_config_id', None)
            return

        proxy_user = pos_config.self_ordering_default_user_id
        if not proxy_user or not proxy_user.active:
            return

        # Per-request elevation: mutate only request.env, never the session.
        request.update_env(user=proxy_user.id)
