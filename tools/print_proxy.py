#!/usr/bin/env python3
"""
ESC/POS Print Proxy Server for Odoo 18 Community Edition.

A lightweight Flask server that receives print jobs from Odoo POS
(base64-encoded JPEG images) and sends them to generic ESC/POS
network printers via TCP port 9100.

Usage:
    pip install flask Pillow

    # Simulator mode (no real printer needed, saves images to disk):
    python print_proxy.py --simulate

    # Real printer mode (also install python-escpos):
    pip install python-escpos
    python print_proxy.py

    # With a custom config:
    python print_proxy.py --config /path/to/print_proxy_config.json

The proxy listens on http://0.0.0.0:8073 by default and accepts
print jobs at POST /hw_proxy/default_printer_action.
"""

import argparse
import base64
import io
import json
import logging
import os
import sys
import time

from flask import Flask, request, jsonify, send_from_directory

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

# python-escpos is optional in simulator mode
NetworkPrinter = None
try:
    from escpos.printer import Network as NetworkPrinter
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('print_proxy')

app = Flask(__name__)

# Default config
DEFAULT_CONFIG = {
    'host': '0.0.0.0',
    'port': 8073,
    'default_printer_ip': '192.168.1.100',
    'default_printer_port': 9100,
    'paper_width': 80,  # mm (58 or 80)
}

config = dict(DEFAULT_CONFIG)

# Runtime state
simulate_mode = False
output_dir = None
print_history = []  # In-memory log of recent prints (simulator mode)


def load_config(path):
    """Load config from JSON file, merging with defaults."""
    if os.path.exists(path):
        with open(path) as f:
            user_config = json.load(f)
        config.update(user_config)
        logger.info("Loaded config from %s", path)
    else:
        logger.info("No config file found at %s, using defaults", path)


# ── Image processing ─────────────────────────────────────────

def decode_receipt_image(image_data_b64):
    """Decode base64 image data and prepare for printing.

    :param image_data_b64: Base64-encoded JPEG image from Odoo POS
    :returns: PIL Image object (monochrome, scaled to paper width)
    """
    img_bytes = base64.b64decode(image_data_b64)
    img = Image.open(io.BytesIO(img_bytes))

    # Scale to printer paper width (80mm ~ 576 dots at 203dpi)
    max_width = 576 if config.get('paper_width', 80) == 80 else 384
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    return img


# ── Real printer functions ────────────────────────────────────

def print_image_real(printer_ip, printer_port, image_data_b64):
    """Send receipt image to a real ESC/POS network printer."""
    if NetworkPrinter is None:
        return {
            'result': False,
            'error': 'python-escpos not installed. '
                     'Install with: pip install python-escpos',
        }

    img = decode_receipt_image(image_data_b64)

    # Convert to monochrome for thermal printing
    if img.mode != '1':
        img = img.convert('L').point(lambda x: 0 if x < 128 else 255, '1')

    printer = NetworkPrinter(printer_ip, port=printer_port, timeout=10)
    try:
        printer.image(img, impl='bitImageRaster')
        printer.cut()
    finally:
        printer.close()

    logger.info("Printed receipt to %s:%s", printer_ip, printer_port)
    return {'result': True}


def open_cashbox_real(printer_ip, printer_port):
    """Send cash drawer kick pulse to a real printer."""
    if NetworkPrinter is None:
        return {
            'result': False,
            'error': 'python-escpos not installed.',
        }

    printer = NetworkPrinter(printer_ip, port=printer_port, timeout=10)
    try:
        printer.cashdraw(2)
    finally:
        printer.close()

    logger.info("Opened cashbox via %s:%s", printer_ip, printer_port)
    return {'result': True}


# ── Simulator functions ───────────────────────────────────────

def print_image_simulate(printer_ip, printer_port, image_data_b64):
    """Save receipt image to disk instead of sending to a printer."""
    img = decode_receipt_image(image_data_b64)

    timestamp = time.strftime('%Y%m%d_%H%M%S')
    filename = f"receipt_{timestamp}_{printer_ip}.png"
    filepath = os.path.join(output_dir, filename)
    img.save(filepath)

    entry = {
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'action': 'print_receipt',
        'printer_ip': printer_ip,
        'printer_port': printer_port,
        'filename': filename,
        'image_size': f"{img.width}x{img.height}",
    }
    print_history.append(entry)
    # Keep last 50 entries
    if len(print_history) > 50:
        print_history.pop(0)

    logger.info(
        "SIMULATE: Saved receipt to %s (%dx%d px)",
        filepath, img.width, img.height,
    )
    return {'result': True}


def open_cashbox_simulate(printer_ip, printer_port):
    """Log cashbox open event (no actual hardware action)."""
    entry = {
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'action': 'cashbox',
        'printer_ip': printer_ip,
        'printer_port': printer_port,
    }
    print_history.append(entry)
    if len(print_history) > 50:
        print_history.pop(0)

    logger.info("SIMULATE: Cashbox open pulse to %s:%s", printer_ip, printer_port)
    return {'result': True}


# ── Routes ────────────────────────────────────────────────────

@app.route('/hw_proxy/default_printer_action', methods=['POST', 'OPTIONS'])
def printer_action():
    """Handle print jobs from Odoo POS relay controller."""
    # CORS preflight
    if request.method == 'OPTIONS':
        resp = jsonify({})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    try:
        body = request.get_json(force=True)
        data = body.get('params', {}).get('data', {})
        action = data.get('action', '')

        # Determine target printer
        printer_ip = data.get('printer_ip') or config['default_printer_ip']
        printer_port = int(data.get('printer_port', config['default_printer_port']))

        if action == 'print_receipt':
            receipt = data.get('receipt', '')
            if not receipt:
                return jsonify({'result': False, 'error': 'No receipt data'})
            if simulate_mode:
                result = print_image_simulate(printer_ip, printer_port, receipt)
            else:
                result = print_image_real(printer_ip, printer_port, receipt)
            return jsonify(result)

        elif action == 'cashbox':
            if simulate_mode:
                result = open_cashbox_simulate(printer_ip, printer_port)
            else:
                result = open_cashbox_real(printer_ip, printer_port)
            return jsonify(result)

        else:
            return jsonify({'result': False, 'error': f'Unknown action: {action}'})

    except Exception as e:
        logger.exception("Print action failed")
        return jsonify({'result': False, 'error': str(e)})


@app.route('/status', methods=['GET'])
def status():
    """Health check endpoint."""
    return jsonify({
        'status': 'running',
        'mode': 'simulator' if simulate_mode else 'real',
        'default_printer': f"{config['default_printer_ip']}:{config['default_printer_port']}",
        'paper_width': config['paper_width'],
        'output_dir': output_dir if simulate_mode else None,
    })


@app.route('/history', methods=['GET'])
def history():
    """View recent print history (simulator mode)."""
    return jsonify({
        'mode': 'simulator' if simulate_mode else 'real',
        'count': len(print_history),
        'history': list(reversed(print_history)),
    })


@app.route('/receipts/<path:filename>', methods=['GET'])
def serve_receipt(filename):
    """Serve saved receipt images (simulator mode)."""
    if not simulate_mode or not output_dir:
        return jsonify({'error': 'Only available in simulator mode'}), 404
    return send_from_directory(output_dir, filename)


@app.route('/', methods=['GET'])
def index():
    """Dashboard page showing proxy status and recent receipts."""
    mode_badge = (
        '<span style="color:#0a0;font-weight:bold">SIMULATOR</span>'
        if simulate_mode else
        '<span style="color:#00a;font-weight:bold">REAL PRINTER</span>'
    )

    receipts_html = ''
    if simulate_mode:
        for entry in reversed(print_history):
            if entry.get('action') == 'print_receipt' and entry.get('filename'):
                receipts_html += (
                    f'<div style="display:inline-block;margin:10px;'
                    f'border:1px solid #ccc;padding:10px;background:#fff;">'
                    f'<div style="font-size:12px;color:#666;">'
                    f'{entry["time"]} | {entry["printer_ip"]} | '
                    f'{entry["image_size"]}</div>'
                    f'<img src="/receipts/{entry["filename"]}" '
                    f'style="max-width:400px;margin-top:5px;" />'
                    f'</div><br/>'
                )

    if not receipts_html and simulate_mode:
        receipts_html = (
            '<p style="color:#999;">No receipts yet. '
            'Send an order from Odoo POS to see receipts here.</p>'
        )

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>ESC/POS Print Proxy</title>
    <meta charset="utf-8"/>
    <meta http-equiv="refresh" content="5"/>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px;
               background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .info {{ background: #fff; padding: 15px; border-radius: 8px;
                margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
        .info p {{ margin: 5px 0; }}
    </style>
</head>
<body>
    <h1>ESC/POS Print Proxy</h1>
    <div class="info">
        <p>Mode: {mode_badge}</p>
        <p>Default Printer: {config['default_printer_ip']}:{config['default_printer_port']}</p>
        <p>Paper Width: {config['paper_width']}mm</p>
        <p>Total Jobs: {len(print_history)}</p>
        {'<p>Output Dir: ' + output_dir + '</p>' if simulate_mode else ''}
    </div>
    <h2>Recent Receipts</h2>
    {receipts_html if simulate_mode else
     '<p style="color:#999;">Receipt preview only available in simulator mode. '
     'Start with: python print_proxy.py --simulate</p>'}
    <hr style="margin-top:30px;"/>
    <p style="font-size:12px;color:#999;">
        API: POST /hw_proxy/default_printer_action |
        <a href="/status">Status JSON</a> |
        <a href="/history">History JSON</a> |
        Auto-refreshes every 5 seconds
    </p>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────

def main():
    global simulate_mode, output_dir

    parser = argparse.ArgumentParser(
        description='ESC/POS Print Proxy for Odoo POS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simulator mode (no printer needed, saves images to disk):
  python print_proxy.py --simulate

  # Real printer mode:
  python print_proxy.py

  # Custom output directory for receipts:
  python print_proxy.py --simulate --output /tmp/receipts
        """,
    )
    parser.add_argument(
        '--config', '-c',
        default=os.path.join(os.path.dirname(__file__), 'print_proxy_config.json'),
        help='Path to config JSON file',
    )
    parser.add_argument(
        '--simulate', '-s',
        action='store_true',
        help='Simulator mode: save receipt images to disk instead of printing',
    )
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Output directory for simulated receipts (default: ./print_output)',
    )
    parser.add_argument('--host', default=None, help='Listen host (overrides config)')
    parser.add_argument('--port', type=int, default=None, help='Listen port (overrides config)')
    args = parser.parse_args()

    load_config(args.config)

    simulate_mode = args.simulate
    if simulate_mode:
        output_dir = args.output or os.path.join(
            os.path.dirname(__file__), 'print_output'
        )
        os.makedirs(output_dir, exist_ok=True)
        logger.info("SIMULATOR MODE: Receipts will be saved to %s", output_dir)

        if NetworkPrinter is None:
            logger.info(
                "python-escpos not installed (not needed in simulator mode)"
            )
    else:
        if NetworkPrinter is None:
            logger.error(
                "python-escpos is required for real printer mode. "
                "Install with: pip install python-escpos"
            )
            logger.error(
                "Or use --simulate for simulator mode (no printer needed)"
            )
            sys.exit(1)

    host = args.host or config['host']
    port = args.port or config['port']

    logger.info("Starting ESC/POS Print Proxy on %s:%s", host, port)
    if not simulate_mode:
        logger.info(
            "Default printer: %s:%s (%dmm paper)",
            config['default_printer_ip'],
            config['default_printer_port'],
            config['paper_width'],
        )
    logger.info("Dashboard: http://localhost:%s", port)

    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    main()
