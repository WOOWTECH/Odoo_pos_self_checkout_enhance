/** @odoo-module */

import { FloorScreen } from "@pos_restaurant/app/floor_screen/floor_screen";
import { patch } from "@web/core/utils/patch";

patch(FloorScreen.prototype, {
    getKdsReadyCount(table) {
        return this.pos.models["pos.order"].filter((o) => {
            if (o.table_id?.id !== table.id || o.finalized) return false;
            if (!o.kds_sent_to_kitchen) return false;
            if (o.kds_state === "served") return false;
            // Check for done-but-not-served items
            try {
                const rawDone = o.kds_done_items;
                const done = typeof rawDone === "string" ? JSON.parse(rawDone || "{}") : (rawDone || {});
                const rawServed = o.kds_served_items;
                const served = typeof rawServed === "string" ? JSON.parse(rawServed || "{}") : (rawServed || {});
                return Object.entries(done).some(([k, v]) => v === true && !served[k]);
            } catch (e) {
                return false;
            }
        }).length;
    },
});
