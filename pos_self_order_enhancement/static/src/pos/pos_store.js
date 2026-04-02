/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

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
                        const fired = JSON.parse(order.kds_fired_courses || "{}");
                        fired[String(data.course_fired)] = true;
                        order.kds_fired_courses = JSON.stringify(fired);
                    } catch (e) { /* ignore */ }
                }
                if (data.kds_done_items !== undefined) {
                    order.kds_done_items = data.kds_done_items;
                }
            }
        }
    },

    async markOrderServed(order) {
        if (typeof order.id === "number") {
            try {
                await this.data.call("pos.order", "mark_served", [[order.id]]);
                order.kds_state = "served";
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
                    const fired = JSON.parse(order.kds_fired_courses || "{}");
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

    /**
     * Get course groups for the current order.
     * Returns [{id, name, is_fired}] sorted by name.
     */
    getOrderCourseGroups(order) {
        if (!order || !order.lines) return [];

        let fired = {};
        try {
            fired = JSON.parse(order.kds_fired_courses || "{}");
        } catch (e) { /* ignore */ }

        const groups = {};
        for (const line of order.lines) {
            if (line.qty <= 0) continue;
            const categs = line.product_id?.pos_categ_ids;
            if (!categs || categs.length === 0) continue;
            const categ = Array.isArray(categs) ? categs[0] : categs;
            if (!categ.kds_hold_fire) continue;

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
                // Update local state so fire buttons appear immediately
                order.kds_sent_to_kitchen = true;
                const categories = {};
                for (const line of order.lines) {
                    if (line.qty <= 0) continue;
                    const categs = line.product_id?.pos_categ_ids;
                    if (!categs || categs.length === 0) continue;
                    const categ = Array.isArray(categs) ? categs[0] : categs;
                    if (!categ.kds_hold_fire) continue;
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
