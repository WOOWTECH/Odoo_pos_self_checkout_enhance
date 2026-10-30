# -*- coding: utf-8 -*-
"""Pre-migration: drop FK on ecpay_invoice_id before Many2one → Integer conversion.

ecpay_invoice_id used to be a Many2one('uniform.invoice'). We are changing it
to a plain Integer so the module no longer hard-depends on ecpay_invoice_tw.

The underlying PostgreSQL column is already integer (Many2one stores the id),
so no data conversion is needed. But the FK constraint must be removed first,
otherwise the ORM update will fail if the uniform_invoice table has been
dropped (ecpay_invoice_tw uninstalled).
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info(
        "pre-migration 18.0.1.4.0: dropping FK constraint on pos_order.ecpay_invoice_id"
    )
    cr.execute("""
        DO $$
        DECLARE
            _constraint text;
        BEGIN
            SELECT conname INTO _constraint
              FROM pg_constraint
             WHERE conrelid = 'pos_order'::regclass
               AND conname LIKE '%%ecpay_invoice_id%%'
               AND contype = 'f';

            IF _constraint IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE pos_order DROP CONSTRAINT %I',
                    _constraint
                );
                RAISE NOTICE 'Dropped FK constraint: %', _constraint;
            ELSE
                RAISE NOTICE 'No FK constraint found on ecpay_invoice_id — nothing to drop';
            END IF;
        EXCEPTION WHEN undefined_table THEN
            RAISE NOTICE 'pos_order table does not exist — skipping';
        END $$;
    """)
