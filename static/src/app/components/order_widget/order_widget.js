/** @odoo-module */

import { OrderWidget } from "@pos_self_order/app/components/order_widget/order_widget";
import { patch } from "@web/core/utils/patch";

patch(OrderWidget.prototype, {
    get lineNotSend() {
        const original = super.lineNotSend;
        const payAfter = this.selfOrder.config.self_ordering_pay_after;

        // In meal mode with no pending changes, show full order total
        // instead of confusing "0 items $0.00"
        if (payAfter === "meal" && original.count === 0) {
            const order = this.selfOrder.currentOrder;
            if (order.lines.length > 0) {
                return {
                    count: order.lines.filter((l) => !l.combo_parent_id).length,
                    price: order.get_total_with_tax(),
                };
            }
        }

        return original;
    },
});
