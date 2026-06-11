/** @odoo-module **/
import { EatingLocationPage } from "@pos_self_order/app/pages/eating_location_page/eating_location_page";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(EatingLocationPage.prototype, {
    setup() {
        super.setup(...arguments);
        const url = new URL(window.location.href);
        this.isDineIn = url.searchParams.has("table_identifier");
    },

    get pageTitle() {
        return this.isDineIn ? _t("內用點餐") : _t("外帶點餐");
    },

    get cardLabel() {
        return this.isDineIn ? _t("堂食") : _t("外賣");
    },

    get enterLabel() {
        return _t("進入");
    },

    get enterAriaLabel() {
        return this.isDineIn ? _t("進入內用點餐") : _t("進入外帶點餐");
    },

    get tableInfo() {
        const table = this.selfOrder.currentTable;
        if (!table) {
            return "";
        }
        const floor = table.floor_id?.name ?? "";
        const num = String(table.table_number ?? "");
        if (floor) {
            return `${floor} - ${num} ${_t("號桌")}`;
        }
        return `${num} ${_t("號桌")}`;
    },

    enter() {
        this.selectLocation(this.isDineIn ? "in" : "out");
    },
});
