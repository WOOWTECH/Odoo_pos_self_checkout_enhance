/** @odoo-module **/
import { EatingLocationPage } from "@pos_self_order/app/pages/eating_location_page/eating_location_page";
import { patch } from "@web/core/utils/patch";

patch(EatingLocationPage.prototype, {
    setup() {
        super.setup(...arguments);
        const url = new URL(window.location.href);
        this.isTakeawayUrl = !url.searchParams.has("table_identifier");
        this.isDineInUrl = url.searchParams.has("table_identifier");
    },

    /** Table info string for dine-in welcome page */
    get tableInfo() {
        const table = this.selfOrder.currentTable;
        if (!table) {
            return "";
        }
        const floor = table.floor_id?.name || "";
        const num = table.table_number || "";
        return floor ? `${floor} - ${num} 號桌` : `${num} 號桌`;
    },

    /** One-tap enter for takeaway URL */
    enterTakeaway() {
        this.selectLocation("out");
    },

    /** One-tap enter for dine-in URL */
    enterDineIn() {
        this.selectLocation("in");
    },
});
