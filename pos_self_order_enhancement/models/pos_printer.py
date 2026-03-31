from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


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
