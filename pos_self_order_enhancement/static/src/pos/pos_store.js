/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

/**
 * Safely get the first pos.category with kds_hold_fire from a product.
 * Handles ORM proxy objects for Many2many fields.
 * Returns {id, name, kds_hold_fire} or null.
 */
function getHoldFireCategory(line) {
    try {
        const product = line.product_id;
        if (!product) return null;
        const categs = product.pos_categ_ids;
        if (!categs) return null;
        // Handle both array and ORM proxy
        let first = null;
        if (typeof categs[Symbol.iterator] === "function") {
            for (const c of categs) {
                first = c;
                break;
            }
        } else if (categs[0]) {
            first = categs[0];
        }
        if (!first || !first.kds_hold_fire) return null;
        return first;
    } catch (e) {
        return null;
    }
}

patch(PosStore.prototype, {
    async initServerData() {
        const result = await super.initServerData(...arguments);
        this.data.connectWebSocket("KDS_ORDER_UPDATE", (data) => {
            this._onKdsOrderUpdate(data);
        });
        return result;
    },

    _onKdsOrderUpdate(data) {
        if (data.order_id) {
            const order = this.models["pos.order"].find(
                (o) => o.id === data.order_id
            );
            if (order) {
                order.kds_state = data.kds_state;
                if (data.course_fired !== undefined) {
                    try {
                        const raw = order.kds_fired_courses;
                        const fired = typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
                        fired[String(data.course_fired)] = true;
                        order.kds_fired_courses = JSON.stringify(fired);
                    } catch (e) { /* ignore */ }
                }
                if (data.kds_done_items !== undefined) {
                    order.kds_done_items = data.kds_done_items;
                }
                if (data.kds_served_items !== undefined) {
                    order.kds_served_items = data.kds_served_items;
                }
                if (data.kds_remake_data !== undefined) {
                    order.kds_remake_data = data.kds_remake_data;
                }
            }
        }
    },

    async markOrderServed(order) {
        if (typeof order.id === "number") {
            try {
                await this.data.call("pos.order", "mark_served", [[order.id]]);
                // Update local served items — mark all done items as served
                try {
                    const rawDone = order.kds_done_items;
                    const done = typeof rawDone === "string" ? JSON.parse(rawDone || "{}") : (rawDone || {});
                    const rawServed = order.kds_served_items;
                    const served = typeof rawServed === "string" ? JSON.parse(rawServed || "{}") : (rawServed || {});
                    for (const [k, v] of Object.entries(done)) {
                        if (v) served[k] = true;
                    }
                    order.kds_served_items = JSON.stringify(served);
                    // Check if all items served — backend will set kds_state
                    const allServed = (order.lines || [])
                        .filter(l => l.qty > 0)
                        .every(l => served[String(l.id)]);
                    if (allServed) {
                        order.kds_state = "served";
                    }
                } catch (e) { /* ignore */ }
            } catch (e) {
                console.warn("KDS mark_served failed:", e);
            }
        }
    },

    async markOrderRemake(order, lineIds, reason) {
        if (typeof order.id === "number") {
            try {
                await this.data.call("pos.order", "mark_remake", [
                    [order.id],
                    lineIds,
                    reason,
                ]);
                order.kds_state = "new";
            } catch (e) {
                console.warn("KDS mark_remake failed:", e);
            }
        }
    },

    async fireOrderCourse(order, categoryId) {
        if (typeof order.id === "number") {
            try {
                await this.data.call("pos.order", "fire_course", [
                    [order.id],
                    categoryId,
                ]);
                try {
                    const raw = order.kds_fired_courses;
                    const fired = typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
                    fired[String(categoryId)] = true;
                    order.kds_fired_courses = JSON.stringify(fired);
                } catch (e) { /* ignore */ }
                if (order.kds_state === "done") {
                    order.kds_state = "in_progress";
                }
            } catch (e) {
                console.warn("KDS fire_course failed:", e);
            }
        }
    },

    getOrderCourseGroups(order) {
        try {
            if (!order || !order.lines) return [];

            let fired = {};
            try {
                const raw = order.kds_fired_courses;
                fired = typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
            } catch (e) { /* ignore */ }

            const groups = {};
            for (const line of order.lines) {
                if (line.qty <= 0) continue;
                const categ = getHoldFireCategory(line);
                if (!categ) continue;

                const cid = categ.id;
                if (!groups[cid]) {
                    groups[cid] = {
                        id: cid,
                        name: categ.name || `Category ${cid}`,
                        is_fired: !!fired[String(cid)],
                    };
                }
            }

            return Object.values(groups).sort((a, b) => a.name.localeCompare(b.name));
        } catch (e) {
            return [];
        }
    },

    async sendOrderInPreparation(order, cancelled = false) {
        await super.sendOrderInPreparation(order, cancelled);

        if (typeof order.id !== "number") {
            await this.syncAllOrders({ orders: [order] });
        }

        if (typeof order.id === "number") {
            try {
                await this.data.call(
                    "pos.order",
                    "mark_sent_to_kitchen",
                    [[order.id]]
                );
                order.kds_sent_to_kitchen = true;
                const categories = {};
                for (const line of order.lines) {
                    if (line.qty <= 0) continue;
                    const categ = getHoldFireCategory(line);
                    if (!categ) continue;
                    categories[categ.id] = categ.name || "";
                }
                if (Object.keys(categories).length > 0) {
                    const sorted = Object.entries(categories).sort((a, b) => a[1].localeCompare(b[1]));
                    const firstId = parseInt(sorted[0][0]);
                    const fired = {};
                    for (const [cid] of sorted) {
                        fired[cid] = (parseInt(cid) === firstId);
                    }
                    order.kds_fired_courses = JSON.stringify(fired);
                }
            } catch (e) {
                console.warn("KDS mark_sent_to_kitchen failed:", e);
            }
        }
    },
});
