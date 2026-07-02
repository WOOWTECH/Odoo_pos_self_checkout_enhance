/** @odoo-module **/
import { Component } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/self_order_service";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * DeliveryOptionPage - Choose between pickup (自取) and delivery (外送).
 *
 * Only shown when:
 *   - User selected takeaway (外帶) on the eating location page
 *   - Config has uber_direct_enabled = true
 *
 * Flow:
 *   EatingLocationPage → DeliveryOptionPage → ProductListPage  (pickup)
 *   EatingLocationPage → DeliveryOptionPage → DeliveryAddressPage  (delivery)
 */
export class DeliveryOptionPage extends Component {
    static template = "pos_self_order_enhancement.DeliveryOptionPage";
    static props = {};

    setup() {
        this.selfOrder = useSelfOrder();
        this.router = useService("router");
    }

    get pickupLabel() {
        return _t("自取");
    }

    get pickupDescription() {
        return _t("到店取餐");
    }

    get deliveryLabel() {
        return _t("外送");
    }

    get deliveryDescription() {
        return _t("送餐到府");
    }

    get pageTitle() {
        return _t("取餐方式");
    }

    selectPickup() {
        // Clear any previous delivery data
        const order = this.selfOrder.currentOrder;
        order.uber_delivery_address = false;
        order.uber_delivery_name = false;
        order.uber_delivery_phone = false;
        order.uber_delivery_fee = 0;
        order.uber_quote_id = false;
        this.router.navigate("product_list");
    }

    selectDelivery() {
        this.router.navigate("delivery_address");
    }

    back() {
        this.router.navigate("default");
    }
}
