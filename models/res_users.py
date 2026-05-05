from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _get_portal_pos_configs(self):
        """Return the pos.config recordset this portal user may access.

        Access is derived from the employee linked to the user
        (``hr.employee.user_id``) and the POS config's employee-login
        settings (``module_pos_hr``, ``basic_employee_ids``,
        ``advanced_employee_ids``).

        Rules:
        - The user must have an ``hr.employee`` record.
        - The POS config must have ``module_pos_hr`` enabled (Log in with
          Employees).
        - If ``basic_employee_ids`` is empty ("All Employees"), any
          employee may access.
        - Otherwise the employee must appear in ``basic_employee_ids``
          or ``advanced_employee_ids``.
        """
        self.ensure_one()
        Employee = self.env['hr.employee'].sudo()
        employee = Employee.search([('user_id', '=', self.id)], limit=1)
        if not employee:
            return self.env['pos.config']

        PosConfig = self.env['pos.config'].sudo()
        configs = PosConfig.search([
            ('active', '=', True),
            ('module_pos_hr', '=', True),
        ])

        result = self.env['pos.config']
        for cfg in configs:
            if not cfg.basic_employee_ids:
                # "All Employees" — any employee may access.
                result |= cfg
            elif employee in cfg.basic_employee_ids or employee in cfg.advanced_employee_ids:
                result |= cfg
        return result
