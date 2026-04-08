/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

/**
 * Safely get the first pos.category with kds_hold_fire from a product.
 * Handles ORM proxy objects for Many2many fields.
 * Returns {id, name, kds_hold_fire} or null.
 */
export function getHoldFireCategory(line) {
    try {
        // Combo children inherit their combo parent's Hold & Fire category,
        // so they follow the parent's held/fired state.
        const effective = line.combo_parent_id || line;
        const product = effective.product_id;
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

                // Print the lines that just became eligible. Held lines were
                // never recorded in last_order_preparation_change (because
                // _applyHoldFireSkipChange marked them skip_change=true on
                // the original Order click), so the diff machinery now sees
                // them as new and prints only the newly fired category.
                await this.sendOrderInPreparation(order, false);
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

    /**
     * Hold & Fire gating for kitchen printing.
     *
     * Walks the order's lines and sets `line.skip_change` based on whether
     * each line's Hold & Fire category is currently fired. Combo children
     * inherit their parent's category via getHoldFireCategory.
     *
     *   - No Hold & Fire category → skip_change=false (always print)
     *   - Held category            → skip_change=true  (excluded from diff,
     *                                                    not recorded in
     *                                                    last_order_preparation_change)
     *   - Fired category           → skip_change=false (printed normally)
     *
     * Upstream's getOrderChanges (utils/order_change.js) gates each line on
     * `orderline.skip_change === skipped` and updateLastOrderChange skips
     * lines where `!line.skip_change` is false — together those mean a held
     * line is invisible to the printer until its category is fired, at
     * which point fireOrderCourse re-runs sendOrderInPreparation and the
     * now-eligible lines appear in the diff naturally.
     */
    _applyHoldFireSkipChange(order) {
        let fired = {};
        try {
            const raw = order.kds_fired_courses;
            fired = typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
        } catch (e) { /* ignore */ }

        for (const line of order.lines) {
            if (line.qty <= 0) continue;
            const categ = getHoldFireCategory(line);
            if (!categ) {
                line.skip_change = false;
            } else {
                line.skip_change = !fired[String(categ.id)];
            }
        }
    },

    async sendOrderInPreparation(order, cancelled = false) {
        // Gate held lines out of the print diff. They stay queued until
        // the cashier fires their category, at which point fireOrderCourse
        // re-invokes this method.
        this._applyHoldFireSkipChange(order);

        await super.sendOrderInPreparation(order, cancelled);

        // Always flush pending lines to the backend so the custom KDS
        // (which reads pos.order.line directly) sees them immediately,
        // including on second/third Order clicks against the same order.
        await this.syncAllOrders({ orders: [order] });

        if (typeof order.id === "number") {
            try {
                await this.data.call(
                    "pos.order",
                    "mark_sent_to_kitchen",
                    [[order.id]]
                );
                order.kds_sent_to_kitchen = true;
                // All Hold & Fire categories start held — staff fires manually from POS.
                const categoryIds = new Set();
                for (const line of order.lines) {
                    if (line.qty <= 0) continue;
                    const categ = getHoldFireCategory(line);
                    if (!categ) continue;
                    categoryIds.add(categ.id);
                }
                if (categoryIds.size > 0) {
                    const fired = {};
                    for (const cid of categoryIds) {
                        fired[String(cid)] = false;
                    }
                    order.kds_fired_courses = JSON.stringify(fired);
                }
            } catch (e) {
                console.warn("KDS mark_sent_to_kitchen failed:", e);
            }
        }
    },
});
