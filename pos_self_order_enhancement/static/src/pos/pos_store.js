/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async sendOrderInPreparation(order, cancelled = false) {
        await super.sendOrderInPreparation(order, cancelled);
        // Mark order as sent to kitchen via direct RPC call.
        // Cannot use order.kds_sent_to_kitchen = true because the OWL data model
        // doesn't include this field in its schema, so serialize({orm: true}) ignores it.
        if (order.id) {
            try {
                await this.data.call(
                    "pos.order",
                    "mark_sent_to_kitchen",
                    [[order.id]]
                );
            } catch (e) {
                console.warn("KDS mark_sent_to_kitchen failed:", e);
            }
        }
    },
});
