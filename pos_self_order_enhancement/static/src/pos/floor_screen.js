/** @odoo-module */

import { FloorScreen } from "@pos_restaurant/app/floor_screen/floor_screen";
import { patch } from "@web/core/utils/patch";

function parseJson(raw) {
    try {
        return typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
    } catch (e) {
        return {};
    }
}

patch(FloorScreen.prototype, {
    getCounterPayCount(table) {
        return this.pos.models["pos.order"].filter((o) => {
            if (o.table_id?.id !== table.id || o.finalized) return false;
            return o.self_order_payment_status === "pending_counter";
        }).length;
    },

    getKdsReadyCount(table) {
        return this.pos.models["pos.order"].filter((o) => {
            if (o.table_id?.id !== table.id || o.finalized) return false;
            if (!o.kds_sent_to_kitchen) return false;
            if (o.kds_state === "served") return false;
            // Check for done-but-not-served items
            const done = parseJson(o.kds_done_items);
            const served = parseJson(o.kds_served_items);
            return Object.entries(done).some(([k, v]) => v === true && !served[k]);
        }).length;
    },

    getKdsHoldCount(table) {
        return this.pos.models["pos.order"].filter((o) => {
            if (o.table_id?.id !== table.id || o.finalized) return false;
            if (!o.kds_sent_to_kitchen) return false;
            if (o.kds_state === "served") return false;
            // Has at least one held (not fired) category?
            const fired = parseJson(o.kds_fired_courses);
            const hasHeld = Object.values(fired).some((v) => v === false);
            if (!hasHeld) return false;
            // Suppress when Ready takes precedence: any done-but-not-served items
            const done = parseJson(o.kds_done_items);
            const served = parseJson(o.kds_served_items);
            const hasReady = Object.entries(done).some(([k, v]) => v === true && !served[k]);
            return !hasReady;
        }).length;
    },
});
