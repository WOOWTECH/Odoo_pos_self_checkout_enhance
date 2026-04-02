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
                    // Update local fired courses state
                    try {
                        const fired = JSON.parse(order.kds_fired_courses || "{}");
                        fired[String(data.course_fired)] = true;
                        order.kds_fired_courses = JSON.stringify(fired);
                    } catch (e) { /* ignore */ }
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

    async fireOrderCourse(order, courseSequence) {
        if (typeof order.id === "number") {
            try {
                await this.data.call("pos.order", "fire_course", [
                    [order.id],
                    courseSequence,
                ]);
                // Update local state
                try {
                    const fired = JSON.parse(order.kds_fired_courses || "{}");
                    fired[String(courseSequence)] = true;
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
     * Returns [{sequence, name, is_fired, all_done}] sorted by sequence.
     */
    getOrderCourseGroups(order) {
        if (!order || !order.lines) return [];

        let fired = {};
        try {
            fired = JSON.parse(order.kds_fired_courses || "{}");
        } catch (e) { /* ignore */ }

        const groups = {};  // seq -> {sequence, name, is_fired}
        for (const line of order.lines) {
            if (line.qty <= 0) continue;
            const categs = line.product_id?.pos_categ_ids;
            let seq = 0;
            let name = "";
            if (categs && categs.length > 0) {
                const categ = Array.isArray(categs) ? categs[0] : categs;
                seq = categ.kds_course_sequence || 0;
                name = categ.name || "";
            }
            if (seq === 0) continue;

            if (!groups[seq]) {
                groups[seq] = {
                    sequence: seq,
                    name: name || `Course ${seq}`,
                    is_fired: !!fired[String(seq)],
                };
            }
        }

        return Object.values(groups).sort((a, b) => a.sequence - b.sequence);
    },

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
