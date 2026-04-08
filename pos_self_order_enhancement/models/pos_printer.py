import base64
import io

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError

from ..vendor.escpos_min import print_image


class PosPrinter(models.Model):
    _inherit = 'pos.printer'

    printer_type = fields.Selection(
        selection_add=[('network_escpos', 'Use a network ESC/POS printer')]
    )
    escpos_printer_ip = fields.Char(
        string='Printer IP Address',
        help='IP address of the ESC/POS network printer (e.g., 192.168.1.100)',
        default='192.168.1.100',
    )

    @api.constrains('escpos_printer_ip')
    def _constrains_escpos_printer_ip(self):
        for record in self:
            if record.printer_type == 'network_escpos' and not record.escpos_printer_ip:
                raise ValidationError(_("Printer IP Address cannot be empty."))

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        params += ['escpos_printer_ip']
        return params

    def action_print_test_page(self):
        """Render and send a small test ticket to the configured printer.

        Used by the "Print test page" button on the printer form view to
        verify connectivity + raster encoding without going through a real
        POS order.
        """
        self.ensure_one()
        if self.printer_type != 'network_escpos':
            raise UserError(_(
                "The test print only supports the 'network ESC/POS printer' type."
            ))
        if not self.escpos_printer_ip:
            raise UserError(_("Please set the printer IP address first."))

        # Build a tiny test bitmap with Pillow (already in base Odoo).
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('1', (576, 240), 1)  # 80 mm @ 203 dpi, white bg
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        lines = [
            "POS SELF ORDER ENHANCEMENT",
            "ESC/POS network printer test",
            "",
            f"Printer: {self.name or '(unnamed)'}",
            f"IP:      {self.escpos_printer_ip}",
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
                    "A test ticket has been sent to %s. "
                    "Check the printer."
                ) % self.escpos_printer_ip,
                'type': 'success',
                'sticky': False,
            },
        }
