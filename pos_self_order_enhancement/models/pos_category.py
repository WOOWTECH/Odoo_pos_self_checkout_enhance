from odoo import models, fields, api


class PosCategory(models.Model):
    _inherit = 'pos.category'

    kds_course_sequence = fields.Integer(
        string='Course Sequence',
        default=0,
        help='Items in categories with the same sequence fire together as one course. '
             'Lower numbers fire first. 0 = fires immediately (no course grouping).',
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        result += ['kds_course_sequence']
        return result
