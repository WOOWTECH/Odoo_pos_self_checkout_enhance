/** @odoo-module */

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

patch(PosOrderline.prototype, {
    getDisplayData() {
        const data = super.getDisplayData();
        try {
            const order = this.order_id;
            if (order && typeof order.id === "number" && order.kds_sent_to_kitchen) {
                const raw = order.kds_done_items;
                const doneItems = typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
                data.kdsStatus = doneItems[String(this.id)] ? "done" : "pending";
            }
        } catch (e) {
            // Silently ignore — line may not be saved yet
        }
        return data;
    },
});
