# -*- coding: utf-8 -*-
"""
Minimal in-process ESC/POS network printer driver.

Replaces the external `tools/print_proxy.py` Flask + python-escpos service so
the addon has zero pip dependencies beyond what base Odoo already ships
(Pillow). Network printers only — TCP socket to port 9100, raster bitmap
output. No text/codepage logic; the POS frontend already renders the receipt
as a JPEG via Odoo's existing Epson ePOS canvas pipeline.

Public API:
    print_image(printer_ip, port, b64_jpeg, paper_width=80, timeout=3)
    open_cashbox(printer_ip, port=9100, timeout=3)
"""
import base64
import io
import logging
import socket

from PIL import Image  # hard dep of base Odoo

_logger = logging.getLogger(__name__)

# ── ESC/POS command bytes ─────────────────────────────────────
ESC = b'\x1b'
GS = b'\x1d'

CMD_INIT = ESC + b'@'
CMD_CUT = GS + b'V\x00'  # full cut
# Cashbox kick: ESC p m t1 t2 — pin 2, on=25 ms, off=255 ms
CMD_CASHBOX_KICK = ESC + b'p\x00\x19\xff'

PAPER_WIDTH_DOTS = {
    80: 576,  # 80 mm @ 203 dpi ≈ 576 dots
    58: 384,  # 58 mm @ 203 dpi ≈ 384 dots
}


def _decode_to_monochrome(b64_jpeg, paper_width):
    """Decode the base64 JPEG and return a 1-bit PIL image at printer width.

    The frontend always sends a JPEG ≤ printer width; we still clamp in case
    a future change pushes a larger image through.
    """
    img_bytes = base64.b64decode(b64_jpeg)
    img = Image.open(io.BytesIO(img_bytes))

    max_width = PAPER_WIDTH_DOTS.get(paper_width, PAPER_WIDTH_DOTS[80])
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    if img.mode != '1':
        img = img.convert('L').point(lambda x: 0 if x < 128 else 255, '1')

    return img


def _image_to_raster(img):
    """Encode a 1-bit PIL image as ESC/POS raster bit-image bytes.

    Wire format (GS v 0):
        1D 76 30 m xL xH yL yH <bitmap>
        m       = 0 (normal mode)
        xL,xH   = bytes per row, little-endian
        yL,yH   = number of rows, little-endian
        bitmap  = row-major, MSB first, 1 bit per pixel, 1 = black
    """
    width, height = img.size
    bytes_per_row = (width + 7) // 8

    # Pad each row to the byte boundary
    padded = Image.new('1', (bytes_per_row * 8, height), 1)
    padded.paste(img, (0, 0))

    # PIL '1' mode: 0 = black, 255 = white
    # ESC/POS raster: 1 = black, 0 = white → invert
    raw = padded.tobytes()
    inverted = bytes(b ^ 0xFF for b in raw)

    header = (
        GS + b'v0\x00'
        + bytes([bytes_per_row & 0xFF, (bytes_per_row >> 8) & 0xFF])
        + bytes([height & 0xFF, (height >> 8) & 0xFF])
    )
    return header + inverted


def _send_bytes(printer_ip, port, payload, timeout):
    """Open a socket, send the payload, close. Raises OSError on failure."""
    with socket.create_connection((printer_ip, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload)


def print_image(printer_ip, port, b64_jpeg, paper_width=80, timeout=3):
    """Decode the JPEG receipt and print it on a network ESC/POS printer.

    :returns: dict {'success': bool, 'error': str | None}
    """
    if not printer_ip:
        return {'success': False, 'error': 'printer_ip is empty'}
    if not b64_jpeg:
        return {'success': False, 'error': 'receipt payload is empty'}

    try:
        img = _decode_to_monochrome(b64_jpeg, paper_width)
    except Exception as e:
        _logger.exception("ESC/POS image decode failed")
        return {'success': False, 'error': f'decode failed: {e}'}

    try:
        payload = CMD_INIT + _image_to_raster(img) + b'\n\n\n' + CMD_CUT
        _send_bytes(printer_ip, port, payload, timeout)
        _logger.info(
            "ESC/POS printed receipt to %s:%s (%dx%d)",
            printer_ip, port, img.width, img.height,
        )
        return {'success': True, 'error': None}
    except OSError as e:
        _logger.warning("ESC/POS print failed for %s:%s: %s", printer_ip, port, e)
        return {'success': False, 'error': f'printer unreachable: {e}'}
    except Exception as e:
        _logger.exception("ESC/POS print failed unexpectedly")
        return {'success': False, 'error': str(e)}


def open_cashbox(printer_ip, port=9100, timeout=3):
    """Send a cash drawer kick pulse to a network ESC/POS printer.

    :returns: dict {'success': bool, 'error': str | None}
    """
    if not printer_ip:
        return {'success': False, 'error': 'printer_ip is empty'}

    try:
        _send_bytes(printer_ip, port, CMD_INIT + CMD_CASHBOX_KICK, timeout)
        _logger.info("ESC/POS opened cashbox via %s:%s", printer_ip, port)
        return {'success': True, 'error': None}
    except OSError as e:
        _logger.warning("ESC/POS cashbox failed for %s:%s: %s", printer_ip, port, e)
        return {'success': False, 'error': f'printer unreachable: {e}'}
    except Exception as e:
        _logger.exception("ESC/POS cashbox failed unexpectedly")
        return {'success': False, 'error': str(e)}
