/** @odoo-module */

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";

patch(ControlButtons.prototype, {
    get orderIsKdsReady() {
        const order = this.pos.get_order();
        return order && order.kds_state === "done";
    },

    async onClickServed() {
        const order = this.pos.get_order();
        if (order) {
            await this.pos.markOrderServed(order);
        }
    },
});
