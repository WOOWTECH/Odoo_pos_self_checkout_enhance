/** @odoo-module */

import { SelfOrder } from "@pos_self_order/app/self_order_service";
import { patch } from "@web/core/utils/patch";

patch(SelfOrder.prototype, {
    /**
     * Override initMobileData to detect table switches.
     * When the URL table_identifier differs from the in-memory currentTable,
     * clear stale orders before fetching orders for the new table.
     */
    async initMobileData() {
        const urlTableId = this.router.getTableIdentifier();

        if (urlTableId) {
            // Check if any existing orders belong to a different table
            const urlTable = this.models["restaurant.table"].find(
                (t) => t.identifier === urlTableId
            );
            const existingOrders = this.models["pos.order"].getAll();
            const hasStaleOrders = existingOrders.some(
                (o) => o.table_id && o.table_id.identifier !== urlTableId
            );

            if (hasStaleOrders) {
                for (const order of existingOrders) {
                    order.delete();
                }
                this.selectedOrderUuid = null;
                this.currentTable = null;
            }
        }

        return super.initMobileData();
    },
});
