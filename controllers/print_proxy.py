# -*- coding: utf-8 -*-
import base64
import io
import logging

from odoo import http
from odoo.http import request

from ..vendor.escpos_min import print_image, open_cashbox

_logger = logging.getLogger(__name__)

# Default ESC/POS network printer port
DEFAULT_PRINTER_PORT = 9100
# Socket timeout (seconds). Short on purpose: an offline printer must not
# stall an Odoo HTTP worker.
PRINTER_TIMEOUT = 3

# A real kitchen ticket JPEG is typically 5–50 KB. An all-white canvas
# rendered by html-to-image (CJK font embedding failure or background tab
# throttling) produces a tiny JPEG of ~500–2000 bytes. We treat anything
# below this threshold as "blank" and log a warning.
BLANK_IMAGE_THRESHOLD = 2500


class PosEscPosProxy(http.Controller):
    """In-process ESC/POS print controller.

    Two endpoints:
      /pos-escpos/print        — browser-rendered JPEG receipt (legacy)
      /pos-escpos/print-order  — server-side Pillow rendering (preferred)
    """

    # ── Server-side rendering endpoint (preferred) ─────────

    @http.route('/pos-escpos/print-order', type='json', auth='user', methods=['POST'])
    def print_order_server_side(self, order_id, printer_id, title='New', lines=None):
        """Render a kitchen ticket server-side with Pillow and send to printer.

        Completely bypasses the browser html-to-image pipeline, avoiding
        blank receipts from CJK font embedding failures in SVG foreignObject.

        :param order_id: pos.order record id
        :param printer_id: pos.printer record id
        :param title: Ticket title (e.g. 'New', 'Cancelled')
        :param lines: List of dicts with {name, quantity, note}
        :returns: dict with 'success' boolean
        """
        printer = self._find_printer(printer_id=printer_id)
        if not printer or not printer.escpos_proxy_url:
            return {'success': False, 'error': 'No relay-configured printer found'}

        Order = request.env['pos.order'].sudo()
        order = Order.browse(int(order_id)).exists()
        if not order:
            return {'success': False, 'error': f'Order {order_id} not found'}

        b64_jpeg = self._render_ticket_image(order, printer, title, lines or [])
        if not b64_jpeg:
            return {'success': False, 'error': 'Failed to render ticket image'}

        return printer._send_via_relay(b64_jpeg)

    @staticmethod
    def _render_ticket_image(order, printer, title, lines):
        """Render a kitchen ticket as a JPEG image using Pillow.

        Returns base64-encoded JPEG string, or None on failure.
        """
        from PIL import Image, ImageDraw, ImageFont

        pw = int(printer.escpos_paper_width or '80')
        dots = {80: 576, 58: 384}.get(pw, 576)

        # Load CJK font
        font_large = font_med = font_small = None
        for font_path in [
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
        ]:
            try:
                font_large = ImageFont.truetype(font_path, 28)
                font_med = ImageFont.truetype(font_path, 22)
                font_small = ImageFont.truetype(font_path, 18)
                break
            except (OSError, IOError):
                continue
        if not font_large:
            try:
                font_large = ImageFont.load_default(size=28)
                font_med = ImageFont.load_default(size=22)
                font_small = ImageFont.load_default(size=18)
            except TypeError:
                font_large = font_med = font_small = ImageFont.load_default()

        margin = 10
        y = margin
        content = []

        # Header: order reference
        ref = order.pos_reference or order.name or ''
        content.append(('large', ref, True))
        y += 36

        # Table info
        if order.table_id:
            floor = order.table_id.floor_id.name if order.table_id.floor_id else ''
            tnum = order.table_id.table_number or ''
            table_str = f"{floor} - {tnum}" if floor else str(tnum)
            content.append(('med', table_str, True))
            y += 30

        # Takeaway / Delivery indicator
        if order.uber_delivery_address:
            content.append(('med', '*** 外送 ***', True))
            y += 30
            addr = order.uber_delivery_address or ''
            if len(addr) > 30:
                content.append(('small', addr[:30], True))
                y += 24
                content.append(('small', addr[30:60], True))
                y += 24
            else:
                content.append(('small', addr, True))
                y += 24
            if order.uber_courier_name:
                content.append(('small', f"騎手: {order.uber_courier_name}", True))
                y += 24
        elif order.takeaway:
            content.append(('med', '*** 外帶 ***', True))
            y += 30

        content.append(('sep', '', False))
        y += 10

        # Use frontend-provided lines if available, otherwise fall back to order.lines
        if lines:
            for line in lines:
                name = line.get('name', '')
                qty = line.get('quantity', 1)
                qty_str = int(qty) if qty == int(qty) else qty
                content.append(('med', f"{qty_str}x  {name}", False))
                y += 28
                note = line.get('note', '')
                if note:
                    content.append(('small', f"  ** {note}", False))
                    y += 24
        else:
            for line in order.lines.filtered(lambda l: l.qty > 0):
                name = line.full_product_name or line.product_id.display_name or ''
                qty = int(line.qty) if line.qty == int(line.qty) else line.qty
                content.append(('med', f"{qty}x  {name}", False))
                y += 28
                line_note = getattr(line, 'note', '') or ''
                if line_note:
                    content.append(('small', f"  ** {line_note}", False))
                    y += 24

        # General note
        general_note = order.general_note or ''
        if general_note:
            content.append(('sep', '', False))
            y += 10
            content.append(('small', f"備註: {general_note}", False))
            y += 24

        y += margin

        # Create image
        img = Image.new('RGB', (dots, max(y, 100)), 'white')
        draw = ImageDraw.Draw(img)

        y = margin
        for fkey, text, center in content:
            if fkey == 'sep':
                draw.line([(margin, y + 4), (dots - margin, y + 4)], fill='black', width=2)
                y += 10
                continue
            font = {'large': font_large, 'med': font_med, 'small': font_small}[fkey]
            line_h = {'large': 36, 'med': 28, 'small': 24}[fkey]
            if center:
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                x = max(margin, (dots - tw) // 2)
            else:
                x = margin
            draw.text((x, y), text, fill='black', font=font)
            y += line_h

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85)
        _logger.info(
            "[escpos] server-side rendered ticket for %s: %dx%d, %d bytes",
            order.name or order.pos_reference, img.size[0], img.size[1], len(buf.getvalue()),
        )
        return base64.b64encode(buf.getvalue()).decode('ascii')

    # ── Browser-rendered JPEG endpoint (legacy/fallback) ───

    @http.route('/pos-escpos/print', type='json', auth='user', methods=['POST'])
    def relay_print(self, action, printer_id=None, printer_ip=None, receipt=None):
        """Print a receipt or kick the cash drawer."""
        printer = self._find_printer(printer_id=printer_id, printer_ip=printer_ip)

        if action == 'print_receipt':
            if receipt:
                image_bytes = self._safe_b64decode(receipt)
                if image_bytes is not None:
                    img_size = len(image_bytes)
                    _logger.info("[escpos] browser image: %d bytes", img_size)
                    if img_size < BLANK_IMAGE_THRESHOLD:
                        _logger.warning(
                            "[escpos] browser image suspiciously small (%d bytes < %d), "
                            "likely blank from html-to-image CJK failure",
                            img_size, BLANK_IMAGE_THRESHOLD,
                        )

            if printer and printer.escpos_proxy_url:
                return printer._send_via_relay(receipt)
            ip = (printer.escpos_printer_ip if printer else '') or printer_ip
            if not ip:
                return {'success': False, 'error': 'No printer IP available.'}
            pw = int(printer.escpos_paper_width or '80') if printer else 80
            copies = printer.escpos_print_copies if printer else 1
            _logger.info("[escpos] local TCP -> %s (paper=%dmm, copies=%d)", ip, pw, copies)
            return print_image(
                ip, DEFAULT_PRINTER_PORT, receipt,
                paper_width=pw, copies=copies, timeout=PRINTER_TIMEOUT,
            )

        if action == 'cashbox':
            if printer and printer.escpos_proxy_url:
                return {'success': False, 'error': 'Cashbox not supported over cloud relay.'}
            ip = (printer.escpos_printer_ip if printer else '') or printer_ip
            if not ip:
                return {'success': False, 'error': 'No printer IP available.'}
            return open_cashbox(ip, port=DEFAULT_PRINTER_PORT, timeout=PRINTER_TIMEOUT)

        return {'success': False, 'error': f'Unknown action: {action}'}

    @staticmethod
    def _safe_b64decode(data):
        try:
            return base64.b64decode(data)
        except Exception:
            return None

    @staticmethod
    def _find_printer(printer_id=None, printer_ip=None):
        Printer = request.env['pos.printer'].sudo()
        if printer_id:
            try:
                return Printer.browse(int(printer_id)).exists()
            except (ValueError, TypeError):
                pass
        if printer_ip:
            return Printer.search([('escpos_printer_ip', '=', printer_ip)], limit=1)
        return Printer
