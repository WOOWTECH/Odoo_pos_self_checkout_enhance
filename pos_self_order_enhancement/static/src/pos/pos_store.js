/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async sendOrderInPreparation(order, cancelled = false) {
        await super.sendOrderInPreparation(order, cancelled);
        // Mark order as sent to kitchen by staff for KDS display
        if (!order.kds_sent_to_kitchen) {
            order.kds_sent_to_kitchen = true;
            await this.syncAllOrders({ orders: [order] });
        }
    },
});
