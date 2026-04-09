/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";
import { changesToOrder } from "@point_of_sale/app/models/utils/order_change";

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
        if (typeof order.id !== "number") return;
        try {
            await this.data.call("pos.order", "mark_remake", [
                [order.id],
                lineIds,
                reason,
            ]);
            order.kds_state = "new";
        } catch (e) {
            console.warn("KDS mark_remake failed:", e);
            return;
        }

        // Resolve the explicitly-selected lines.
        const remakeLines = order.lines.filter(
            (l) => lineIds.includes(l.id) && l.qty > 0
        );
        if (!remakeLines.length) return;

        // Auto-pull combo children of any selected parent into the remake
        // set so the kitchen ticket shows the full combo, not just the
        // parent slot. (parent → children only, never child → siblings.)
        const remakeUuids = new Set(remakeLines.map((l) => l.uuid));
        for (const line of order.lines) {
            if (line.qty <= 0) continue;
            if (remakeUuids.has(line.uuid)) continue;
            const parent = line.combo_parent_id;
            if (parent && remakeUuids.has(parent.uuid)) {
                remakeLines.push(line);
                remakeUuids.add(line.uuid);
            }
        }

        // Build a synthetic orderChange directly from the explicit remake
        // lines, bypassing the changesToOrder diff (which would otherwise
        // include held-and-not-yet-fired siblings as "new" because they
        // were intentionally excluded from last_order_preparation_change).
        // The lineDetails shape mirrors upstream getOrderChanges
        // (utils/order_change.js:70-82) so the receipt template renders
        // the same as a normal kitchen ticket.
        const buildLineDetails = (line) => {
            const product = line.product_id;
            const categs = product.pos_categ_ids || [];
            const firstCateg = categs[0] && categs[0].id ? categs[0] : null;
            return {
                uuid: line.uuid,
                name:
                    typeof line.get_full_product_name === "function"
                        ? line.get_full_product_name()
                        : product.display_name,
                basic_name: product.name,
                isCombo: line.combo_item_id?.id,
                product_id: product.id,
                attribute_value_ids: line.attribute_value_ids,
                quantity: line.qty,
                note:
                    typeof line.getNote === "function"
                        ? line.getNote()
                        : line.note ?? "",
                pos_categ_id: firstCateg?.id ?? 0,
                pos_categ_sequence: firstCateg?.sequence ?? 0,
                display_name: product.display_name,
            };
        };

        const orderChange = {
            new: remakeLines.map(buildLineDetails),
            cancelled: [],
            noteUpdated: [],
            generalNote: undefined,
            modeUpdate: false,
        };

        // _remakeReason makes printReceipts swap the title to
        // "REMAKE (<reason>)". _comboMaps lets _getPrintingCategoriesChanges
        // keep combo children with their parents through the per-printer
        // category filter. last_order_preparation_change is intentionally
        // NOT touched, so the next Order click sees an unchanged baseline.
        order._remakeReason = reason;
        this._comboMaps = this._buildComboMaps(order);
        try {
            await this.printChanges(order, orderChange);
        } catch (e) {
            console.warn("REMAKE print failed:", e);
        } finally {
            order._remakeReason = null;
            this._comboMaps = null;
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
     * Build maps for combo parent/child relationships in an order.
     * Used by _getPrintingCategoriesChanges so combo children pass the
     * per-printer category filter alongside their parents (the children's
     * own product categories often differ from the parent's).
     */
    _buildComboMaps(order) {
        const parentUuidByChild = new Map();
        const childUuidsByParent = new Map();
        for (const line of order.lines) {
            if (line.qty <= 0) continue;
            const parent = line.combo_parent_id;
            if (!parent || !parent.uuid) continue;
            parentUuidByChild.set(line.uuid, parent.uuid);
            if (!childUuidsByParent.has(parent.uuid)) {
                childUuidsByParent.set(parent.uuid, new Set());
            }
            childUuidsByParent.get(parent.uuid).add(line.uuid);
        }
        return { parentUuidByChild, childUuidsByParent };
    },

    /**
     * Patch upstream's per-printer category filter so that any combo child
     * whose parent passes is also admitted, regardless of the child's own
     * pos_categ_ids. Without this, combo "choices" silently disappear from
     * kitchen tickets when their products live in non-printer categories.
     */
    _getPrintingCategoriesChanges(categories, currentOrderChange) {
        const base = super._getPrintingCategoriesChanges(categories, currentOrderChange);
        const maps = this._comboMaps;
        if (!maps || !maps.childUuidsByParent.size) return base;

        // Collect uuids of parents that survived the standard filter in any bucket.
        const passingParentUuids = new Set();
        for (const bucket of [base.new, base.cancelled, base.noteUpdated]) {
            for (const c of bucket) {
                if (maps.childUuidsByParent.has(c.uuid)) {
                    passingParentUuids.add(c.uuid);
                }
            }
        }
        if (!passingParentUuids.size) return base;

        const augment = (filteredBucket, sourceBucket) => {
            const out = [...filteredBucket];
            const present = new Set(out.map((c) => c.uuid));
            for (const change of sourceBucket || []) {
                if (present.has(change.uuid)) continue;
                const parentUuid = maps.parentUuidByChild.get(change.uuid);
                if (parentUuid && passingParentUuids.has(parentUuid)) {
                    out.push(change);
                    present.add(change.uuid);
                }
            }
            return out;
        };

        return {
            new: augment(base.new, currentOrderChange.new),
            cancelled: augment(base.cancelled, currentOrderChange.cancelled),
            noteUpdated: augment(base.noteUpdated, currentOrderChange.noteUpdated),
        };
    },

    /**
     * Substitute the kitchen-ticket title when we're inside a REMAKE flow,
     * so the printed paper is clearly distinguishable from a normal Order
     * ticket. Falls through to upstream behavior otherwise.
     */
    async printReceipts(order, printer, title, lines, fullReceipt = false, diningModeUpdate) {
        let effectiveTitle = title;
        if (order && order._remakeReason && title === "New") {
            effectiveTitle = "REMAKE (" + order._remakeReason + ")";
        }
        return super.printReceipts(
            order,
            printer,
            effectiveTitle,
            lines,
            fullReceipt,
            diningModeUpdate
        );
    },

    _getFiredCoursesMap(order) {
        try {
            const raw = order.kds_fired_courses;
            return typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
        } catch (e) {
            return {};
        }
    },

    /**
     * Hold & Fire gating for kitchen printing.
     *
     * We override sendOrderInPreparation entirely (instead of mutating
     * `line.skip_change` and delegating to super) because skip_change is a
     * persisted Boolean field and any sync round-trip can re-hydrate it
     * from the DB default, silently undoing the gate. Instead we:
     *
     *   1. Compute the upstream diff via changesToOrder().
     *   2. Filter held lines out of every bucket the printer consumes.
     *   3. Print the filtered diff ourselves.
     *   4. Update last_order_preparation_change with held lines temporarily
     *      flagged skip_change=true (restored synchronously in finally),
     *      so the next sendOrderInPreparation (e.g. after fireOrderCourse)
     *      naturally sees the now-fired lines as a fresh diff and prints
     *      them exactly once.
     *
     * `kds_fired_courses` is the single source of truth for hold/fire
     * state, matching what the KDS already does via getHoldFireCategory.
     */
    async sendOrderInPreparation(order, cancelled = false) {
        const fired = this._getFiredCoursesMap(order);
        const isHeld = (line) => {
            if (!line || line.qty <= 0) return false;
            const categ = getHoldFireCategory(line);
            return !!categ && !fired[String(categ.id)];
        };
        const heldUuids = new Set(
            order.lines.filter(isHeld).map((l) => l.uuid)
        );

        if (this.printers_category_ids_set && this.printers_category_ids_set.size) {
            const orderChange = changesToOrder(
                order,
                false,
                this.printers_category_ids_set,
                cancelled
            );

            orderChange.new = (orderChange.new || []).filter(
                (c) => !heldUuids.has(c.uuid)
            );
            orderChange.cancelled = (orderChange.cancelled || []).filter(
                (c) => !heldUuids.has(c.uuid)
            );
            orderChange.noteUpdated = (orderChange.noteUpdated || []).filter(
                (c) => !heldUuids.has(c.uuid)
            );

            // The standalone "Message" ticket duplicates the order note that
            // already appears in the items ticket header — suppress it
            // unconditionally so each Order click produces exactly one
            // physical ticket per printer.
            orderChange.generalNote = undefined;

            this._comboMaps = this._buildComboMaps(order);
            try {
                await this.printChanges(order, orderChange);
            } catch (e) {
                console.warn("Hold & Fire printChanges failed:", e);
            } finally {
                this._comboMaps = null;
            }
        }

        // Update last_order_preparation_change but exclude held lines, so
        // they appear as new on the next send (after firing). Restore
        // skip_change synchronously before any sync can persist it.
        const tempSkip = [];
        for (const line of order.lines) {
            if (heldUuids.has(line.uuid)) {
                tempSkip.push([line, line.skip_change]);
                line.skip_change = true;
            }
        }
        try {
            order.updateLastOrderChange();
        } finally {
            for (const [line, prev] of tempSkip) {
                line.skip_change = prev;
            }
        }

        // Flush to backend so the custom KDS (which reads pos.order.line
        // directly) sees the lines immediately, including on subsequent
        // Order clicks against the same order.
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
                    const existing = this._getFiredCoursesMap(order);
                    const merged = {};
                    for (const cid of categoryIds) {
                        const key = String(cid);
                        merged[key] = !!existing[key];
                    }
                    order.kds_fired_courses = JSON.stringify(merged);
                }
            } catch (e) {
                console.warn("KDS mark_sent_to_kitchen failed:", e);
            }
        }
    },
});
