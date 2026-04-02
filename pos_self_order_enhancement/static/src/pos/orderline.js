/** @odoo-module */

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

patch(PosOrderline.prototype, {
    getDisplayData() {
        const data = super.getDisplayData();
        const order = this.order_id;
        if (order && order.kds_sent_to_kitchen) {
            try {
                const doneItems = JSON.parse(order.kds_done_items || "{}");
                data.kdsStatus = doneItems[String(this.id)] ? "done" : "pending";
            } catch (e) {
                data.kdsStatus = null;
            }
        }
        return data;
    },
});
