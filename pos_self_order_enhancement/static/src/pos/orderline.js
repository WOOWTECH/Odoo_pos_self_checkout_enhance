/** @odoo-module */

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

patch(PosOrderline.prototype, {
    /**
     * Get KDS done status for this order line.
     * Returns "done", "pending", or null (not sent to kitchen).
     */
    getKdsStatus() {
        try {
            const order = this.order_id;
            if (!order || typeof order.id !== "number" || !order.kds_sent_to_kitchen) {
                return null;
            }
            const raw = order.kds_done_items;
            const doneItems = typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
            return doneItems[String(this.id)] ? "done" : "pending";
        } catch (e) {
            return null;
        }
    },
});
