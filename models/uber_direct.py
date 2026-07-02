import logging
import time

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

# Module-level token cache: {config_id: {"token": str, "expires_at": float}}
_token_cache = {}

SANDBOX_AUTH_URL = "https://sandbox-login.uber.com/oauth/v2/token"
PRODUCTION_AUTH_URL = "https://login.uber.com/oauth/v2/token"
SANDBOX_API_URL = "https://sandbox-api.uber.com"
PRODUCTION_API_URL = "https://api.uber.com"

REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 3


class UberDirect(models.AbstractModel):
    """Uber Direct REST API client for delivery integration.

    This is an AbstractModel (no database table). All state is transient;
    OAuth tokens are cached at the module level keyed by pos.config id.

    The pos.config record passed as ``config`` is expected to carry:
      - uber_direct_client_id
      - uber_direct_client_secret
      - uber_direct_customer_id
      - uber_direct_env   ("sandbox" | "production")

    These fields are defined in Task 002 (pos.config extension).
    """

    _name = "uber.direct"
    _description = "Uber Direct API Client"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _auth_url(config):
        if config.uber_direct_env == "production":
            return PRODUCTION_AUTH_URL
        return SANDBOX_AUTH_URL

    @staticmethod
    def _api_base(config):
        if config.uber_direct_env == "production":
            return PRODUCTION_API_URL
        return SANDBOX_API_URL

    @staticmethod
    def _make_error(message, status_code=None, detail=None):
        """Return a standardised error dict."""
        result = {"success": False, "error": message}
        if status_code is not None:
            result["status_code"] = status_code
        if detail is not None:
            result["detail"] = detail
        return result

    def _request(self, method, url, headers=None, json=None, params=None):
        """Fire an HTTP request with retries and unified error handling.

        Returns the parsed JSON body on success, or raises after
        ``MAX_RETRIES`` consecutive network-level failures.
        """
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                return resp
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                _logger.warning(
                    "[uber-direct] %s %s attempt %d/%d failed: %s",
                    method.upper(), url, attempt, MAX_RETRIES, exc,
                )
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # OAuth 2.0 – Client Credentials
    # ------------------------------------------------------------------

    @api.model
    def _get_access_token(self, config):
        """Obtain a valid OAuth 2.0 bearer token for *config*.

        Tokens are cached in the module-level ``_token_cache`` dict and
        automatically refreshed when they expire (Uber tokens are valid
        for 30 days, but we honour the ``expires_in`` value returned by
        the server).

        Returns:
            dict: ``{"success": True, "token": "..."}`` on success, or
                  ``{"success": False, "error": "..."}`` on failure.
        """
        cached = _token_cache.get(config.id)
        if cached and cached["expires_at"] > time.time():
            _logger.info(
                "[uber-direct] Using cached token for config %s (expires in %ds)",
                config.id,
                int(cached["expires_at"] - time.time()),
            )
            return {"success": True, "token": cached["token"]}

        auth_url = self._auth_url(config)
        _logger.info(
            "[uber-direct] Requesting new access token for config %s from %s",
            config.id, auth_url,
        )

        try:
            resp = self._request("post", auth_url, json={
                "client_id": config.uber_direct_client_id,
                "client_secret": config.uber_direct_client_secret,
                "grant_type": "client_credentials",
                "scope": "eats.deliveries",
            })
        except requests.exceptions.RequestException as exc:
            msg = f"Token request failed after {MAX_RETRIES} retries: {exc}"
            _logger.error("[uber-direct] %s", msg)
            return self._make_error(msg)

        if resp.status_code != 200:
            body = resp.text
            msg = f"Token request returned HTTP {resp.status_code}"
            _logger.error("[uber-direct] %s — %s", msg, body)
            return self._make_error(msg, status_code=resp.status_code, detail=body)

        data = resp.json()
        token = data.get("access_token", "")
        expires_in = data.get("expires_in", 2592000)  # default 30 days

        _token_cache[config.id] = {
            "token": token,
            "expires_at": time.time() + expires_in - 60,  # 60s safety margin
        }

        _logger.info(
            "[uber-direct] Token acquired for config %s, expires in %ds",
            config.id, expires_in,
        )
        return {"success": True, "token": token}

    def _auth_headers(self, config):
        """Return Authorization headers, or an error dict."""
        token_result = self._get_access_token(config)
        if not token_result["success"]:
            return token_result  # propagate error
        return {
            "Authorization": f"Bearer {token_result['token']}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Quote API
    # ------------------------------------------------------------------

    @api.model
    def _get_quote(self, config, pickup_address, dropoff_address):
        """Request a delivery quote from Uber Direct.

        Args:
            config: ``pos.config`` record with Uber Direct credentials.
            pickup_address (str): Full street address of the store.
            dropoff_address (str): Full street address of the customer.

        Returns:
            dict: ``{"success": True, "fee": int, "currency": str,
                      "estimated_pickup_minutes": int, "quote_id": str}``
                  or ``{"success": False, "error": "..."}``
        """
        headers = self._auth_headers(config)
        if isinstance(headers, dict) and not headers.get("Authorization"):
            return headers  # error from _auth_headers

        customer_id = config.uber_direct_customer_id
        url = f"{self._api_base(config)}/v1/customers/{customer_id}/delivery_quotes"
        body = {
            "pickup_address": pickup_address,
            "dropoff_address": dropoff_address,
            "pickup_name": "\u6625\u7f8e\u98df\u5802",  # 春美食堂
            "dropoff_name": "Customer",
        }

        _logger.info(
            "[uber-direct] Requesting quote for config %s: %s -> %s",
            config.id, pickup_address, dropoff_address,
        )

        try:
            resp = self._request("post", url, headers=headers, json=body)
        except requests.exceptions.RequestException as exc:
            msg = f"Quote request failed after {MAX_RETRIES} retries: {exc}"
            _logger.error("[uber-direct] %s", msg)
            return self._make_error(msg)

        if resp.status_code != 200:
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            msg = data.get("message", f"Quote request returned HTTP {resp.status_code}")
            _logger.error("[uber-direct] %s — %s", msg, resp.text)
            return self._make_error(msg, status_code=resp.status_code, detail=data)

        data = resp.json()
        _logger.info(
            "[uber-direct] Quote received for config %s: fee=%s %s, ETA=%s min, quote_id=%s",
            config.id,
            data.get("fee"),
            data.get("currency"),
            data.get("estimated_pickup_minutes"),
            data.get("id"),
        )
        return {
            "success": True,
            "fee": data.get("fee"),
            "currency": data.get("currency", "TWD"),
            "estimated_pickup_minutes": data.get("estimated_pickup_minutes"),
            "quote_id": data.get("id"),
        }

    # ------------------------------------------------------------------
    # Create Delivery
    # ------------------------------------------------------------------

    @api.model
    def _create_delivery(self, config, order):
        """Create an Uber Direct delivery for a POS order.

        Args:
            config: ``pos.config`` record with Uber Direct credentials.
            order: ``pos.order`` record (or dict-like) with delivery details.
                   Expected attributes / keys:
                     - ``uber_direct_dropoff_address``
                     - ``uber_direct_dropoff_name``
                     - ``uber_direct_dropoff_phone``
                     - ``uber_direct_quote_id``
                     - ``lines`` (order lines for manifest)
                     - ``name`` (order reference)

        Returns:
            dict: ``{"success": True, "delivery_id": str,
                      "tracking_url": str, "status": str, ...}``
                  or ``{"success": False, "error": "..."}``
        """
        headers = self._auth_headers(config)
        if isinstance(headers, dict) and not headers.get("Authorization"):
            return headers

        customer_id = config.uber_direct_customer_id
        url = f"{self._api_base(config)}/v1/customers/{customer_id}/deliveries"

        # Build a human-readable manifest from order lines
        if hasattr(order, "lines"):
            # pos.order recordset
            manifest_items = []
            for line in order.lines:
                manifest_items.append({
                    "name": line.full_product_name or line.product_id.name,
                    "quantity": int(line.qty),
                    "size": "small",
                })
        else:
            manifest_items = [{"name": "POS Order", "quantity": 1, "size": "small"}]

        # Determine order reference
        order_ref = getattr(order, "name", None) or getattr(order, "pos_reference", "order")

        body = {
            "pickup": {
                "name": "\u6625\u7f8e\u98df\u5802",  # 春美食堂
                "address": config.uber_direct_pickup_address
                if hasattr(config, "uber_direct_pickup_address")
                else "",
                "phone_number": config.uber_direct_pickup_phone
                if hasattr(config, "uber_direct_pickup_phone")
                else "",
            },
            "dropoff": {
                "name": getattr(order, "uber_direct_dropoff_name", "Customer"),
                "address": getattr(order, "uber_direct_dropoff_address", ""),
                "phone_number": getattr(order, "uber_direct_dropoff_phone", ""),
            },
            "manifest": {
                "reference": order_ref,
                "items": manifest_items,
            },
        }

        # Attach quote_id if available (locks in the quoted price)
        quote_id = getattr(order, "uber_direct_quote_id", None)
        if quote_id:
            body["quote_id"] = quote_id

        _logger.info(
            "[uber-direct] Creating delivery for config %s, order %s",
            config.id, order_ref,
        )

        try:
            resp = self._request("post", url, headers=headers, json=body)
        except requests.exceptions.RequestException as exc:
            msg = f"Create delivery failed after {MAX_RETRIES} retries: {exc}"
            _logger.error("[uber-direct] %s", msg)
            return self._make_error(msg)

        if resp.status_code not in (200, 201):
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            msg = data.get("message", f"Create delivery returned HTTP {resp.status_code}")
            _logger.error("[uber-direct] %s — %s", msg, resp.text)
            return self._make_error(msg, status_code=resp.status_code, detail=data)

        data = resp.json()
        _logger.info(
            "[uber-direct] Delivery created for config %s: id=%s, status=%s, tracking=%s",
            config.id,
            data.get("id"),
            data.get("status"),
            data.get("tracking_url"),
        )
        return {
            "success": True,
            "delivery_id": data.get("id"),
            "tracking_url": data.get("tracking_url", ""),
            "status": data.get("status", ""),
            "courier": data.get("courier", {}),
        }

    # ------------------------------------------------------------------
    # Cancel Delivery
    # ------------------------------------------------------------------

    @api.model
    def _cancel_delivery(self, config, delivery_id):
        """Cancel an existing Uber Direct delivery.

        Args:
            config: ``pos.config`` record with Uber Direct credentials.
            delivery_id (str): The Uber delivery ID to cancel.

        Returns:
            dict: ``{"success": True}`` or ``{"success": False, "error": "..."}``
        """
        headers = self._auth_headers(config)
        if isinstance(headers, dict) and not headers.get("Authorization"):
            return headers

        customer_id = config.uber_direct_customer_id
        url = (
            f"{self._api_base(config)}/v1/customers/{customer_id}"
            f"/deliveries/{delivery_id}/cancel"
        )

        _logger.info(
            "[uber-direct] Cancelling delivery %s for config %s",
            delivery_id, config.id,
        )

        try:
            resp = self._request("post", url, headers=headers)
        except requests.exceptions.RequestException as exc:
            msg = f"Cancel delivery failed after {MAX_RETRIES} retries: {exc}"
            _logger.error("[uber-direct] %s", msg)
            return self._make_error(msg)

        if resp.status_code != 200:
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            msg = data.get("message", f"Cancel delivery returned HTTP {resp.status_code}")
            _logger.error("[uber-direct] %s — %s", msg, resp.text)
            return self._make_error(msg, status_code=resp.status_code, detail=data)

        _logger.info(
            "[uber-direct] Delivery %s cancelled for config %s",
            delivery_id, config.id,
        )
        return {"success": True}

    # ------------------------------------------------------------------
    # Get Delivery Status
    # ------------------------------------------------------------------

    @api.model
    def _get_delivery_status(self, config, delivery_id):
        """Retrieve the current status of an Uber Direct delivery.

        Args:
            config: ``pos.config`` record with Uber Direct credentials.
            delivery_id (str): The Uber delivery ID.

        Returns:
            dict: ``{"success": True, "delivery_id": str, "status": str,
                      "tracking_url": str, "courier": dict, ...}``
                  or ``{"success": False, "error": "..."}``
        """
        headers = self._auth_headers(config)
        if isinstance(headers, dict) and not headers.get("Authorization"):
            return headers

        customer_id = config.uber_direct_customer_id
        url = (
            f"{self._api_base(config)}/v1/customers/{customer_id}"
            f"/deliveries/{delivery_id}"
        )

        _logger.info(
            "[uber-direct] Getting status for delivery %s, config %s",
            delivery_id, config.id,
        )

        try:
            resp = self._request("get", url, headers=headers)
        except requests.exceptions.RequestException as exc:
            msg = f"Get delivery status failed after {MAX_RETRIES} retries: {exc}"
            _logger.error("[uber-direct] %s", msg)
            return self._make_error(msg)

        if resp.status_code != 200:
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            msg = data.get("message", f"Get delivery status returned HTTP {resp.status_code}")
            _logger.error("[uber-direct] %s — %s", msg, resp.text)
            return self._make_error(msg, status_code=resp.status_code, detail=data)

        data = resp.json()
        _logger.info(
            "[uber-direct] Delivery %s status: %s (config %s)",
            delivery_id, data.get("status"), config.id,
        )
        return {
            "success": True,
            "delivery_id": data.get("id"),
            "status": data.get("status", ""),
            "tracking_url": data.get("tracking_url", ""),
            "courier": data.get("courier", {}),
            "dropoff_eta": data.get("dropoff", {}).get("eta"),
        }
