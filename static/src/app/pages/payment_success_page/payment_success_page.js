/** @odoo-module */

import { Component } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/self_order_service";

/**
 * Payment Success Page - displays after successful payment.
 */
export class PaymentSuccessPage extends Component {
    static template = "pos_self_order_enhancement.PaymentSuccessPage";
    static props = {};

    setup() {
        this.selfOrder = useSelfOrder();
        // Use selfOrder's router (L5: consistent with rest of app)
        this.router = this.selfOrder.router;
    }

    get orderReference() {
        const order = this.selfOrder.currentOrder;
        return order?.pos_reference ||
               order?.tracking_number ||
               order?.name ||
               '';
    }

    get paymentAmount() {
        return this.selfOrder.currentOrder?.amount_total || 0;
    }

    /**
     * Format currency using POS currency configuration.
     */
    formatCurrency(amount) {
        const currency = this.selfOrder.currency;
        if (!currency) {
            return String(amount);
        }
        return currency.symbol + ' ' + amount.toFixed(currency.decimal_places || 0);
    }

    orderAgain() {
        this.selfOrder.selectedOrderUuid = null;
        this.router.navigate("default");
    }
}
