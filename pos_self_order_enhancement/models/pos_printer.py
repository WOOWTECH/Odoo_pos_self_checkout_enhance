import base64
import io
import logging

import requests

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError

from ..vendor.escpos_min import print_image

_logger = logging.getLogger(__name__)

# Relay HTTP timeout (seconds). Longer than the local TCP timeout because
# the request traverses Internet + tunnel + LAN before the printer sees it.
RELAY_TIMEOUT = 10


class PosPrinter(models.Model):
    _inherit = 'pos.printer'

    printer_type = fields.Selection(
        selection_add=[('network_escpos', 'Use a network ESC/POS printer')]
    )
    escpos_printer_ip = fields.Char(
        string='Printer IP Address',
        help=(
            'LAN IP of the ESC/POS network printer (e.g., 192.168.1.100). '
            'Required for direct local TCP printing. Optional when Cloud '
            'Relay URL is set — in cloud mode the HA add-on at the shop '
            'knows its own target printer IP.'
        ),
    )
    escpos_proxy_url = fields.Char(
        string='Cloud Relay URL',
        help=(
            'Optional. When set, print jobs are forwarded to this HTTPS URL '
            '(a local ESC/POS print proxy reachable from the Odoo server) '
            'instead of opening a direct TCP connection to the printer. '
            'Leave empty to keep the existing local TCP printing behavior. '
            'Example: https://print.myshop.com'
        ),
    )
    escpos_proxy_api_key = fields.Char(
        string='Cloud Relay API Key',
        help=(
            'Bearer token sent to the cloud relay as '
            'Authorization: Bearer <key>. Only used when Cloud Relay URL '
            'is set. Stored server-side only; never exposed to POS frontend.'
        ),
    )
    escpos_printer_label = fields.Char(
        string='Printer Label',
        help=(
            'Optional label identifying this printer on the HA add-on side '
            '(e.g. "kitchen", "invoice"). Only used when Cloud Relay URL '
            'is set. Must match a label configured in the add-on\'s '
            '"printers" list. Leave empty for single-printer shops — the '
            'add-on will use its default printer.'
        ),
    )

    @api.constrains('printer_type', 'escpos_printer_ip', 'escpos_proxy_url')
    def _constrains_escpos_endpoint(self):
        """A network_escpos printer must be reachable — either by a direct
        LAN IP (local TCP mode) or by a Cloud Relay URL (the HA add-on
        handles the LAN side)."""
        for record in self:
            if record.printer_type != 'network_escpos':
                continue
            if not record.escpos_printer_ip and not record.escpos_proxy_url:
                raise ValidationError(_(
                    "Set either a Printer IP Address (local TCP) or a "
                    "Cloud Relay URL (cloud mode)."
                ))

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        # escpos_proxy_url is exposed so the frontend knows relay mode is active
        # (for UI hints if ever needed). escpos_proxy_api_key is deliberately
        # NOT exposed — it must stay server-side only.
        params += [
            'escpos_printer_ip',
            'escpos_proxy_url',
            'escpos_printer_label',
        ]
        return params

    # ── cloud relay helper (shared with controllers.print_proxy) ────

    def _send_via_relay(self, image_b64):
        """POST the print job to this printer's configured cloud relay.

        Single source of truth for the HTTP relay path. Used by:
          - ``controllers.print_proxy.relay_print`` — runtime POS prints
          - ``action_print_test_page``              — backend "Print test page"

        Returns {'success': bool, 'error': str|None} — identical envelope
        shape to ``escpos_min.print_image`` so every caller branches on a
        single response contract.
        """
        self.ensure_one()
        url = (self.escpos_proxy_url or '').rstrip('/') + '/print'
        api_key = self.escpos_proxy_api_key or ''
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        payload = {
            'image_base64': image_b64,
            'cut': True,
            'beep': False,
        }
        # Resolution precedence mirrors the add-on:
        #   label > ip > add-on default.
        # Label is preferred for multi-printer shops; it lets the cloud
        # stay ignorant of LAN IPs. IP is kept as an override escape hatch
        # for the rare case where an admin really does need to steer by IP.
        if self.escpos_printer_label:
            payload['printer_label'] = self.escpos_printer_label
            target_log = f"label={self.escpos_printer_label}"
        elif self.escpos_printer_ip:
            payload['printer_ip'] = self.escpos_printer_ip
            target_log = f"ip={self.escpos_printer_ip}"
        else:
            target_log = "<add-on default>"
        _logger.info("[escpos] relay -> %s (%s)", url, target_log)
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
        # {success, error} envelope shared with the TCP path.
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code == 200 and body.get('ok'):
            return {'success': True, 'error': None}
        err = body.get('error') or f'relay returned HTTP {resp.status_code}'
        _logger.warning("[escpos] relay refused: %s", err)
        return {'success': False, 'error': err}

    def action_print_test_page(self):
        """Render and send a small test ticket to the configured printer.

        Used by the "Print test page" button on the printer form view to
        verify connectivity + raster encoding without going through a real
        POS order. Honors cloud relay mode when escpos_proxy_url is set —
        this is the easiest way for an admin to end-to-end verify the
        Cloudflare tunnel + HA add-on chain.
        """
        self.ensure_one()
        if self.printer_type != 'network_escpos':
            raise UserError(_(
                "The test print only supports the 'network ESC/POS printer' type."
            ))
        if not self.escpos_printer_ip and not self.escpos_proxy_url:
            raise UserError(_(
                "Set either a Printer IP Address (local TCP) or a "
                "Cloud Relay URL (cloud mode) first."
            ))

        # Build a tiny test bitmap with Pillow (already in base Odoo).
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('1', (576, 240), 1)  # 80 mm @ 203 dpi, white bg
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        mode_label = "cloud relay" if self.escpos_proxy_url else "local TCP"
        if self.escpos_printer_label:
            ip_label = f"label={self.escpos_printer_label}"
        else:
            ip_label = self.escpos_printer_ip or "(from add-on default)"
        lines = [
            "POS SELF ORDER ENHANCEMENT",
            "ESC/POS network printer test",
            "",
            f"Printer: {self.name or '(unnamed)'}",
            f"IP:      {ip_label}",
            f"Mode:    {mode_label}",
            "",
            "Test:    Hello / 12345 / OK",
            "If you can read this, printing works.",
        ]
        y = 10
        for line in lines:
            draw.text((10, y), line, fill=0, font=font)
            y += 24

        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=80)
        b64_jpeg = base64.b64encode(buf.getvalue()).decode('ascii')

        if self.escpos_proxy_url:
            result = self._send_via_relay(b64_jpeg)
        else:
            result = print_image(
                self.escpos_printer_ip,
                9100,
                b64_jpeg,
                paper_width=80,
                timeout=3,
            )
        if not result.get('success'):
            raise UserError(_(
                "Test print failed: %s",
            ) % (result.get('error') or 'unknown error'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Test print sent"),
                'message': _(
                    "A test ticket has been sent to %s via %s. "
                    "Check the printer."
                ) % (ip_label, mode_label),
                'type': 'success',
                'sticky': False,
            },
        }
