# -*- coding: utf-8 -*-
import base64
import io
import logging

from odoo import http
from odoo.exceptions import AccessError
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

# Error returned to the browser; the real cause (socket error, relay
# response, ...) is only written to the server log.
GENERIC_PRINT_ERROR = 'Printing failed. Check the printer and try again.'
MAX_TICKET_LINES = 100
MAX_TICKET_TEXT = 256
MAX_RECEIPT_B64 = 2_000_000
MAX_RECEIPT_BYTES = 1_500_000


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
        self._check_pos_user()
        printer = self._find_printer(printer_id=printer_id)
        if not printer or not printer.escpos_proxy_url:
            return {'success': False, 'error': 'No relay-configured printer found'}

        try:
            order = request.env['pos.order'].browse(int(order_id)).exists()
        except (TypeError, ValueError):
            order = request.env['pos.order']
        if not order or order.sudo().company_id not in request.env.companies:
            return {'success': False, 'error': 'Order not found'}
        order = order.sudo()
        if (order.state == 'cancel' or not order.session_id
                or order.config_id.current_session_id != order.session_id
                or printer not in order.config_id.printer_ids):
            return {'success': False, 'error': 'Printer not available for order'}
        if not self._valid_ticket_input(title, lines):
            return {'success': False, 'error': 'Invalid ticket content'}
        if not lines and len(order.lines) > MAX_TICKET_LINES:
            return {'success': False, 'error': 'Too many order lines'}

        b64_jpeg = self._render_ticket_image(order.sudo(), printer, title, lines or [])
        if not b64_jpeg:
            return {'success': False, 'error': 'Failed to render ticket image'}

        return self._public_result(printer._send_via_relay(b64_jpeg))

    @staticmethod
    def _valid_ticket_input(title, lines):
        if not isinstance(title, str) or len(title) > 80:
            return False
        if lines is None:
            return True
        if not isinstance(lines, list) or len(lines) > MAX_TICKET_LINES:
            return False
        for line in lines:
            if not isinstance(line, dict):
                return False
            if any(not isinstance(line.get(key, ''), str) or len(line.get(key, '')) > MAX_TICKET_TEXT
                   for key in ('name', 'note', 'customer_note')):
                return False
            raw_qty = line.get('quantity', 1)
            if isinstance(raw_qty, str) and len(raw_qty) > 32:
                return False
            try:
                qty = float(raw_qty)
            except (TypeError, ValueError):
                return False
            if not 0 <= qty <= 10000 or qty != qty:
                return False
        return True

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

        # Print timestamp (server time in user/company timezone).
        try:
            from odoo import fields as odoo_fields
            import pytz
            tz_name = (
                request.env.user.tz
                or request.env.company.partner_id.tz
                or 'Asia/Taipei'
            )
            now_local = odoo_fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(pytz.timezone(tz_name))
            ts_str = now_local.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            from datetime import datetime
            ts_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        content.append(('small', ts_str, True))
        y += 24

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
                # Accept both legacy `note` and `customer_note` keys —
                # different callers use different shapes.
                cnote = line.get('customer_note', '')
                note = line.get('note', '')
                if cnote:
                    content.append(('small', f"  ** {cnote}", False))
                    y += 24
                if note and note != cnote:
                    content.append(('small', f"  ** {note}", False))
                    y += 24
        else:
            for line in order.lines.filtered(lambda l: l.qty > 0):
                name = line.full_product_name or line.product_id.display_name or ''
                qty = int(line.qty) if line.qty == int(line.qty) else line.qty
                content.append(('med', f"{qty}x  {name}", False))
                y += 28
                # Kiosk writes customer_note; POS staff write to note. Show both.
                line_cnote = getattr(line, 'customer_note', '') or ''
                line_note = getattr(line, 'note', '') or ''
                if line_cnote:
                    content.append(('small', f"  ** {line_cnote}", False))
                    y += 24
                if line_note and line_note != line_cnote:
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

        # Create image. With `escpos_square_ticket` the canvas is at least
        # as tall as it is wide, so short tickets print as a square block.
        min_height = dots if printer.escpos_square_ticket else 100
        img = Image.new('RGB', (dots, max(y, min_height)), 'white')
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
        """Print a receipt or kick the cash drawer.

        Only printers configured as pos.printer records (and belonging to
        one of the caller's companies) can be reached; a bare ``printer_ip``
        is only used to look such a record up, never to open a connection.
        """
        self._check_pos_user()
        printer = self._find_printer(printer_id=printer_id, printer_ip=printer_ip)
        if not printer:
            return {'success': False, 'error': 'Printer not found'}
        session = self._current_pos_session()
        if not session or printer not in session.config_id.printer_ids:
            return {'success': False, 'error': 'Printer not available for session'}

        if action == 'print_receipt':
            if not isinstance(receipt, str) or not receipt or len(receipt) > MAX_RECEIPT_B64:
                return {'success': False, 'error': 'Invalid receipt'}
            image_bytes = self._safe_b64decode(receipt)
            if image_bytes is None or len(image_bytes) > MAX_RECEIPT_BYTES:
                return {'success': False, 'error': 'Invalid receipt'}
            if image_bytes:
                img_size = len(image_bytes)
                _logger.info("[escpos] browser image: %d bytes", img_size)
                if img_size < BLANK_IMAGE_THRESHOLD:
                    _logger.warning(
                        "[escpos] browser image suspiciously small (%d bytes < %d), "
                        "likely blank from html-to-image CJK failure",
                        img_size, BLANK_IMAGE_THRESHOLD,
                    )

            if printer.escpos_proxy_url:
                return self._public_result(printer._send_via_relay(receipt))
            ip = printer.escpos_printer_ip
            if not ip:
                return {'success': False, 'error': 'No printer IP available.'}
            pw = int(printer.escpos_paper_width or '80')
            copies = printer.escpos_print_copies or 1
            _logger.info("[escpos] local TCP -> %s (paper=%dmm, copies=%d)", ip, pw, copies)
            return self._public_result(print_image(
                ip, DEFAULT_PRINTER_PORT, receipt,
                paper_width=pw, copies=copies, timeout=PRINTER_TIMEOUT,
            ))

        if action == 'cashbox':
            if printer.escpos_proxy_url:
                return {'success': False, 'error': 'Cashbox not supported over cloud relay.'}
            ip = printer.escpos_printer_ip
            if not ip:
                return {'success': False, 'error': 'No printer IP available.'}
            return self._public_result(
                open_cashbox(ip, port=DEFAULT_PRINTER_PORT, timeout=PRINTER_TIMEOUT)
            )

        return {'success': False, 'error': 'Unknown action'}

    @staticmethod
    def _check_pos_user():
        """These routes drive shop hardware: POS users only (not portal users
        nor internal users without Point of Sale access)."""
        if not request.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessError("You are not allowed to use the POS printers.")

    @staticmethod
    def _public_result(result):
        """Strip low-level error details (OSError text, relay responses)."""
        if isinstance(result, dict) and result.get('success'):
            return {'success': True, 'error': None}
        return {'success': False, 'error': GENERIC_PRINT_ERROR}

    @staticmethod
    def _safe_b64decode(data):
        try:
            return base64.b64decode(data, validate=True)
        except Exception:
            return None

    @staticmethod
    def _find_printer(printer_id=None, printer_ip=None):
        """Return the configured ESC/POS printer (sudo) or an empty recordset.

        Lookup runs with the caller's rights (pos.printer is readable by
        POS users) and is restricted to the caller's allowed companies.
        """
        Printer = request.env['pos.printer']
        printer = Printer
        if printer_id:
            try:
                printer = Printer.browse(int(printer_id)).exists()
            except (ValueError, TypeError):
                printer = Printer
        if printer_id is None and not printer and printer_ip and isinstance(printer_ip, str):
            printer = Printer.search([
                ('escpos_printer_ip', '=', printer_ip),
                ('company_id', 'in', request.env.companies.ids),
            ], limit=1)
        printer_sudo = printer.sudo()
        if not printer_sudo or printer_sudo.printer_type != 'network_escpos':
            return Printer
        if printer_sudo.company_id not in request.env.companies:
            return Printer
        return printer_sudo

    @staticmethod
    def _current_pos_session():
        Session = request.env['pos.session'].sudo()
        session_id = request.env.context.get('pos_session_id') or request.session.get('pos_session_id')
        if session_id:
            try:
                session_id = int(session_id)
            except (TypeError, ValueError):
                return Session
            session = Session.browse(session_id).exists()
            if (session and session.state == 'opened'
                    and session.user_id == request.env.user
                    and session.company_id in request.env.companies):
                return session
            return Session
        sessions = Session.search([
            ('user_id', '=', request.env.user.id),
            ('state', '=', 'opened'),
            ('company_id', 'in', request.env.companies.ids),
        ], limit=2)
        return sessions if len(sessions) == 1 else Session
