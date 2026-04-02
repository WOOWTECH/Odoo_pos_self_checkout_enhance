/** @odoo-module */

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { SendBackPopup } from "@pos_self_order_enhancement/pos/send_back_popup";

// Shared helpers for KDS button logic
function getOrderIsKdsReady(pos) {
    const order = pos.get_order();
    return order && order.kds_state === "done";
}

function getOrderCanSendBack(pos) {
    const order = pos.get_order();
    return order && (order.kds_state === "done" || order.kds_state === "served");
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

    const lines = (order.lines || [])
        .filter((l) => l.qty > 0)
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
    const order = pos.get_order();
    if (!order || !order.kds_sent_to_kitchen) return [];
    return pos.getOrderCourseGroups(order);
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
    get orderIsKdsReady() {
        return getOrderIsKdsReady(this.pos);
    },
    get orderCanSendBack() {
        return getOrderCanSendBack(this.pos);
    },
    get courseGroups() {
        return getOrderCourseGroups(this.pos);
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
