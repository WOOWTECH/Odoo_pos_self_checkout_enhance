/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async sendOrderInPreparation(order, cancelled = false) {
        await super.sendOrderInPreparation(order, cancelled);

        // Ensure order is synced to backend (gets numeric DB ID).
        // Core sendOrderInPreparation only syncs when printers are configured;
        // without printers the order stays local with a string ID.
        if (typeof order.id !== "number") {
            await this.syncAllOrders({ orders: [order] });
        }

        // Mark order as sent to kitchen via direct RPC call.
        if (typeof order.id === "number") {
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
