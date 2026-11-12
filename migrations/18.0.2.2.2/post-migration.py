# -*- coding: utf-8 -*-
"""Hide the server-managed courier charge from POS item selection on upgrades."""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE product_template AS template
           SET available_in_pos = FALSE
          FROM product_product AS product
          JOIN ir_model_data AS xmlid
            ON xmlid.model = 'product.product'
           AND xmlid.module = 'pos_self_order_enhancement'
           AND xmlid.name = 'product_product_delivery_fee'
           AND xmlid.res_id = product.id
         WHERE template.id = product.product_tmpl_id
           AND template.available_in_pos = TRUE
    """)
