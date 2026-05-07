"""Migrate res.partner.portal_pos_config_id (Many2one) to
portal_pos_config_ids (Many2many) before the old column is dropped.

Runs BEFORE the module upgrade proper, so the old column still exists and
the new relation table may or may not exist yet (we CREATE IF NOT EXISTS).
"""


def migrate(cr, version):
    # Skip on fresh install
    if not version:
        return

    # The relation table Odoo would auto-create; we pre-create to own the
    # data-seed step and avoid ordering surprises during the upgrade.
    cr.execute("""
        CREATE TABLE IF NOT EXISTS res_partner_pos_config_portal_rel (
            partner_id integer NOT NULL
                REFERENCES res_partner(id) ON DELETE CASCADE,
            config_id  integer NOT NULL
                REFERENCES pos_config(id)  ON DELETE CASCADE,
            PRIMARY KEY (partner_id, config_id)
        );
        CREATE INDEX IF NOT EXISTS
            res_partner_pos_config_portal_rel_config_id_idx
            ON res_partner_pos_config_portal_rel (config_id);
    """)

    # Only seed if the old column still exists (first upgrade to 18.0.1.1.0)
    cr.execute("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'res_partner'
           AND column_name = 'portal_pos_config_id'
    """)
    if not cr.fetchone():
        return

    cr.execute("""
        INSERT INTO res_partner_pos_config_portal_rel (partner_id, config_id)
        SELECT id, portal_pos_config_id
          FROM res_partner
         WHERE portal_pos_config_id IS NOT NULL
        ON CONFLICT DO NOTHING;
    """)
