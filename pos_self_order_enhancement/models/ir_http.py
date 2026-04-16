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
    '/pos/',            # POS page + our own /pos-self-order/, /pos-kds/...
    '/web/dataset/',    # call_kw, call_button, resequence
    '/web/webclient/',  # load_menus, translations, qweb, version_info
    '/web/image/',      # product images used inside the POS UI
    '/web/content/',    # static content (attachments referenced by POS)
    '/web/static/',     # static assets
    '/longpolling/',    # bus notifications
    '/websocket',       # bus websocket
    '/report/',         # receipt/report rendering
)


def _path_allows_swap(path):
    if path in _POS_SWAP_EXACT_PATHS:
        return True
    return any(path.startswith(p) for p in _POS_SWAP_PREFIXES)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

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

        if not _path_allows_swap(request.httprequest.path):
            return

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
