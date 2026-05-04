/** @odoo-module */

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { SendBackPopup } from "@pos_self_order_enhancement/pos/send_back_popup";
import { _t } from "@web/core/l10n/translation";

// Helper: parse KDS JSON fields safely
function parseKdsJson(raw) {
    try {
        return typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
    } catch (e) {
        return {};
    }
}

// Helper: check if order has any done-but-not-served items
function hasReadyItems(order) {
    try {
        const done = parseKdsJson(order.kds_done_items);
        const served = parseKdsJson(order.kds_served_items);
        return Object.entries(done).some(([k, v]) => v === true && !served[k]);
    } catch (e) {
        return false;
    }
}

// Helper: check if order has any served or done items
function hasServedOrDoneItems(order) {
    try {
        const done = parseKdsJson(order.kds_done_items);
        const served = parseKdsJson(order.kds_served_items);
        const hasDone = Object.values(done).some(v => v === true);
        const hasServed = Object.values(served).some(v => v === true);
        return hasDone || hasServed;
    } catch (e) {
        return false;
    }
}

// Shared helpers for KDS button logic
function getOrderIsKdsReady(pos) {
    const order = pos.get_order();
    if (!order || !order.kds_sent_to_kitchen) return false;
    if (order.kds_state === "served") return false;
    return hasReadyItems(order);
}

function getOrderCanSendBack(pos) {
    const order = pos.get_order();
    if (!order || !order.kds_sent_to_kitchen) return false;
    if (order.kds_state === "served") return true;
    return hasServedOrDoneItems(order);
}

async function handleClickServed(pos) {
    const order = pos.get_order();
    if (order) {
        await pos.markOrderServed(order);
    }
}

async function handleClickSendBack(pos, dialog) {
    const order = pos.get_order();
    if (!order) return;

    // Only show items that are done or served (not pending/still cooking)
    const lines = (order.lines || [])
        .filter((l) => {
            if (l.qty <= 0) return false;
            const status = l.getKdsStatus?.() || null;
            return status === "done" || status === "served";
        })
        .map((l) => ({
            id: l.id,
            qty: l.qty,
            product_name:
                l.full_product_name || l.product_id?.display_name || "",
        }));

    const result = await makeAwaitable(dialog, SendBackPopup, { lines });

    if (result && result.lineIds && result.lineIds.length > 0) {
        await pos.markOrderRemake(order, result.lineIds, result.reason);
    }
}

function getOrderCourseGroups(pos) {
    try {
        const order = pos.get_order();
        if (!order || !order.kds_sent_to_kitchen) return [];
        return pos.getOrderCourseGroups(order);
    } catch (e) {
        return [];
    }
}

async function handleFireCourse(pos, categoryId) {
    const order = pos.get_order();
    if (order) {
        await pos.fireOrderCourse(order, categoryId);
    }
}

// Desktop: ControlButtons patch (rendered when !ui.isSmall)
patch(ControlButtons.prototype, {
    get orderIsKdsReady() {
        return getOrderIsKdsReady(this.pos);
    },
    get orderCanSendBack() {
        return getOrderCanSendBack(this.pos);
    },
    get courseGroups() {
        return getOrderCourseGroups(this.pos);
    },
    getFireLabel(cg) {
        return `${cg.name} - ${_t("FIRE")}`;
    },
    async onClickServed() {
        await handleClickServed(this.pos);
    },
    async onClickSendBack() {
        await handleClickSendBack(this.pos, this.dialog);
    },
    async onFireCourse(categoryId) {
        await handleFireCourse(this.pos, categoryId);
    },
});

// Mobile: ProductScreen patch (switchpane is rendered when ui.isSmall)
patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.kdsDialog = useService("dialog");
    },
    /**
     * Override to use product.product image URL instead of product.template.
     * Fixes broken images when POS is behind a reverse proxy (e.g. Cloudflare
     * Tunnel) where the template URL resolves to a wrong port.
     */
    getProductImage(product) {
        return product.getImageUrl();
    },
    get orderIsKdsReady() {
        return getOrderIsKdsReady(this.pos);
    },
    get orderCanSendBack() {
        return getOrderCanSendBack(this.pos);
    },
    get courseGroups() {
        return getOrderCourseGroups(this.pos);
    },
    getFireLabel(cg) {
        return `${cg.name} - ${_t("FIRE")}`;
    },
    async onClickServed() {
        await handleClickServed(this.pos);
    },
    async onClickSendBack() {
        await handleClickSendBack(this.pos, this.kdsDialog);
    },
    async onFireCourse(categoryId) {
        await handleFireCourse(this.pos, categoryId);
    },
});
