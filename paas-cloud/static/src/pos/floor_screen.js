/** @odoo-module */

import { FloorScreen } from "@pos_restaurant/app/floor_screen/floor_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ServedPopup } from "./served_popup";

function parseJson(raw) {
    try {
        return typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
    } catch (e) {
        return {};
    }
}

/**
 * Should this order be considered for table badges?
 * Includes draft orders AND paid gated orders still in kitchen workflow.
 */
function isActiveForBadges(o, tableId) {
    if (o.table_id?.id !== tableId) return false;
    if (!o.finalized) return true;
    // Include paid gated orders still in kitchen workflow
    return o.self_order_payment_status === "paid"
        && o.kds_sent_to_kitchen
        && o.kds_state !== "served";
}

/**
 * Get orders with ready (done-but-not-served) items for a table.
 */
function getReadyOrders(pos, tableId) {
    return pos.models["pos.order"].filter((o) => {
        if (!isActiveForBadges(o, tableId)) return false;
        if (!o.kds_sent_to_kitchen) return false;
        if (o.kds_state === "served") return false;
        const done = parseJson(o.kds_done_items);
        const served = parseJson(o.kds_served_items);
        return Object.entries(done).some(([k, v]) => v === true && !served[k]);
    });
}

patch(FloorScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");
    },

    async onClickTable(table, ev) {
        // Show Served popup when clicking a table with Ready badge
        if (!this.pos.isOrderTransferMode && !this.pos.isEditMode) {
            const readyOrders = getReadyOrders(this.pos, table.id);
            if (readyOrders.length > 0) {
                const order = readyOrders[0];
                const done = parseJson(order.kds_done_items);
                const served = parseJson(order.kds_served_items);
                const items = (order.lines || [])
                    .filter((l) => l.qty > 0 && done[String(l.id)] && !served[String(l.id)])
                    .map((l) => ({
                        id: l.id,
                        name: l.full_product_name || l.product_id?.display_name || "Item",
                        qty: l.qty,
                    }));

                if (items.length > 0) {
                    this.dialog.add(ServedPopup, {
                        tableName: table.getName ? table.getName() : `Table ${table.table_number}`,
                        items,
                        onServed: async () => {
                            await this.pos.markOrderServed(order);
                        },
                    });
                    return;
                }
            }
        }
        return super.onClickTable(table, ev);
    },

    getCounterPayCount(table) {
        return this.pos.models["pos.order"].filter((o) => {
            if (!isActiveForBadges(o, table.id)) return false;
            return o.self_order_payment_status === "pending_counter";
        }).length;
    },

    getKdsReadyCount(table) {
        return getReadyOrders(this.pos, table.id).length;
    },

    getKdsHoldCount(table) {
        return this.pos.models["pos.order"].filter((o) => {
            if (!isActiveForBadges(o, table.id)) return false;
            if (!o.kds_sent_to_kitchen) return false;
            if (o.kds_state === "served") return false;
            const fired = parseJson(o.kds_fired_courses);
            const hasHeld = Object.values(fired).some((v) => v === false);
            if (!hasHeld) return false;
            const done = parseJson(o.kds_done_items);
            const served = parseJson(o.kds_served_items);
            const hasReady = Object.entries(done).some(([k, v]) => v === true && !served[k]);
            return !hasReady;
        }).length;
    },
});
