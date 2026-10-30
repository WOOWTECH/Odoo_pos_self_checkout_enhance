/** @odoo-module **/
import { Component, useState, onMounted } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/self_order_service";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

/**
 * DeliveryQuotePage - Fetch and display an Uber Direct delivery quote.
 *
 * On mount:
 *   - Calls RPC /pos-self/uber-direct/quote with the order's delivery address
 *   - Displays a loading spinner while the request is in-flight
 *
 * Success state:
 *   - Shows delivery fee (e.g. NT$65) and estimated time (e.g. 約 20 分鐘)
 *   - "Confirm" button stores the fee/quote on the order and navigates to product_list
 *
 * Error state:
 *   - Shows error message (e.g. 此地址不在配送範圍內)
 *   - "Retry" button to re-fetch the quote
 *   - "Back" button to return to address page
 */
export class DeliveryQuotePage extends Component {
    static template = "pos_self_order_enhancement.DeliveryQuotePage";
    static props = {};

    setup() {
        this.selfOrder = useSelfOrder();
        this.router = useService("router");
        this.state = useState({
            loading: true,
            fee: 0,
            currency: "TWD",
            estimatedMinutes: 0,
            quoteId: "",
            error: "",
        });
        onMounted(() => this.fetchQuote());
    }

    get pageTitle() {
        return _t("外送報價");
    }

    async fetchQuote() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await rpc("/pos-self/uber-direct/quote", {
                config_id: this.selfOrder.config.id,
                dropoff_address: this.selfOrder.currentOrder.uber_delivery_address,
                dropoff_name: this.selfOrder.currentOrder.uber_delivery_name || "Customer",
                dropoff_phone: this.selfOrder.currentOrder.uber_delivery_phone || "",
            });
            if (result.success) {
                this.state.fee = result.fee;
                this.state.currency = result.currency || "TWD";
                this.state.estimatedMinutes = result.estimated_pickup_minutes || 0;
                this.state.quoteId = result.quote_id || "";
            } else {
                this.state.error = result.error || _t("無法取得外送報價");
            }
        } catch (e) {
            this.state.error = _t("網路連線失敗，請稍後再試");
        }
        this.state.loading = false;
    }

    get formattedFee() {
        return `NT$ ${this.state.fee}`;
    }

    get formattedTime() {
        if (!this.state.estimatedMinutes) {
            return _t("預估時間計算中");
        }
        return `${_t("約")} ${this.state.estimatedMinutes} ${_t("分鐘")}`;
    }

    get deliveryAddress() {
        return this.selfOrder.currentOrder.uber_delivery_address || "";
    }

    get confirmLabel() {
        return _t("確認外送");
    }

    get retryLabel() {
        return _t("重新查詢");
    }

    get backLabel() {
        return _t("返回修改地址");
    }

    confirmDelivery() {
        // Store quote info on order for later use (cart display, order submission)
        const order = this.selfOrder.currentOrder;
        order.uber_delivery_fee = this.state.fee;
        order.uber_quote_id = this.state.quoteId;
        // Navigate to product list to continue ordering
        this.router.navigate("product_list");
    }

    back() {
        this.router.navigate("delivery_address");
    }
}
