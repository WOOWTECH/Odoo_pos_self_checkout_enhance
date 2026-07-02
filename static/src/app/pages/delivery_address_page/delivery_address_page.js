/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/self_order_service";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * DeliveryAddressPage - Enter delivery address for Uber Direct.
 *
 * Collects structured Taiwan address fields:
 *   - city (縣市)
 *   - district (區)
 *   - street (路段)
 *   - detail (詳細地址 — 巷弄號樓)
 *   - name (收件人姓名)
 *   - phone (收件人電話)
 *
 * On submit: combines fields into a full address string, stores on the
 * current order, and navigates to the delivery quote page.
 */
export class DeliveryAddressPage extends Component {
    static template = "pos_self_order_enhancement.DeliveryAddressPage";
    static props = {};

    setup() {
        this.selfOrder = useSelfOrder();
        this.router = useService("router");

        // Pre-fill from existing order data if user navigated back
        const order = this.selfOrder.currentOrder;
        this.state = useState({
            city: order._deliveryCity || "",
            district: order._deliveryDistrict || "",
            street: order._deliveryStreet || "",
            detail: order._deliveryDetail || "",
            name: order.uber_delivery_name || "",
            phone: order.uber_delivery_phone || "",
            error: "",
        });
    }

    get pageTitle() {
        return _t("外送地址");
    }

    get cityLabel() {
        return _t("縣市");
    }

    get districtLabel() {
        return _t("區");
    }

    get streetLabel() {
        return _t("路段");
    }

    get detailLabel() {
        return _t("詳細地址");
    }

    get detailPlaceholder() {
        return _t("巷弄號樓");
    }

    get nameLabel() {
        return _t("收件人姓名");
    }

    get phoneLabel() {
        return _t("收件人電話");
    }

    get submitLabel() {
        return _t("查詢運費");
    }

    get backLabel() {
        return _t("返回");
    }

    /**
     * Taiwan city options for the dropdown.
     */
    get cityOptions() {
        return [
            "台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市",
            "基隆市", "新竹市", "嘉義市",
            "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣",
            "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣",
            "金門縣", "連江縣",
        ];
    }

    onCityChange(ev) {
        this.state.city = ev.target.value;
    }

    onDistrictInput(ev) {
        this.state.district = ev.target.value;
    }

    onStreetInput(ev) {
        this.state.street = ev.target.value;
    }

    onDetailInput(ev) {
        this.state.detail = ev.target.value;
    }

    onNameInput(ev) {
        this.state.name = ev.target.value;
    }

    onPhoneInput(ev) {
        this.state.phone = ev.target.value;
    }

    /**
     * Validate all required fields are filled.
     */
    validate() {
        if (!this.state.city) {
            this.state.error = _t("請選擇縣市");
            return false;
        }
        if (!this.state.district.trim()) {
            this.state.error = _t("請輸入區");
            return false;
        }
        if (!this.state.street.trim()) {
            this.state.error = _t("請輸入路段");
            return false;
        }
        if (!this.state.detail.trim()) {
            this.state.error = _t("請輸入詳細地址");
            return false;
        }
        if (!this.state.name.trim()) {
            this.state.error = _t("請輸入收件人姓名");
            return false;
        }
        if (!this.state.phone.trim()) {
            this.state.error = _t("請輸入收件人電話");
            return false;
        }
        this.state.error = "";
        return true;
    }

    /**
     * Combine address fields into a single string and store on the order.
     */
    submit() {
        if (!this.validate()) {
            return;
        }

        const fullAddress = `${this.state.city}${this.state.district}${this.state.street}${this.state.detail}`;
        const order = this.selfOrder.currentOrder;

        // Store the combined address and contact info on the order
        order.uber_delivery_address = fullAddress;
        order.uber_delivery_name = this.state.name.trim();
        order.uber_delivery_phone = this.state.phone.trim();

        // Also store individual fields for back-navigation pre-fill
        order._deliveryCity = this.state.city;
        order._deliveryDistrict = this.state.district;
        order._deliveryStreet = this.state.street;
        order._deliveryDetail = this.state.detail;

        this.router.navigate("delivery_quote");
    }

    back() {
        this.router.navigate("delivery_option");
    }
}
