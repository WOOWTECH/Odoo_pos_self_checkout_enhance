/** @odoo-module */

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";
import { getHoldFireCategory } from "./pos_store";

patch(PosOrderline.prototype, {
    /**
     * Get KDS status for this order line.
     * Returns "served", "done", "remake", "hold", "pending", or null (not sent to kitchen).
     */
    getKdsStatus() {
        try {
            const order = this.order_id;
            if (!order || typeof order.id !== "number" || !order.kds_sent_to_kitchen) {
                return null;
            }
            const key = String(this.id);

            const rawServed = order.kds_served_items;
            const served = typeof rawServed === "string" ? JSON.parse(rawServed || "{}") : (rawServed || {});
            if (served[key]) return "served";

            const rawDone = order.kds_done_items;
            const done = typeof rawDone === "string" ? JSON.parse(rawDone || "{}") : (rawDone || {});
            if (done[key]) return "done";

            // Check if item was sent back for remake (has remake data but not done)
            const rawRemake = order.kds_remake_data;
            const remake = typeof rawRemake === "string" ? JSON.parse(rawRemake || "{}") : (rawRemake || {});
            if (remake[key] && remake[key].count > 0) return "remake";

            // Hold: line has a Hold & Fire category that is currently held.
            // Combo children inherit their parent's category via getHoldFireCategory.
            const categ = getHoldFireCategory(this);
            if (categ) {
                const rawFired = order.kds_fired_courses;
                const fired = typeof rawFired === "string" ? JSON.parse(rawFired || "{}") : (rawFired || {});
                if (!fired[String(categ.id)]) return "hold";
            }

            return "pending";
        } catch (e) {
            return null;
        }
    },
});
