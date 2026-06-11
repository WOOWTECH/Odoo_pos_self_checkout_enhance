/** @odoo-module **/
import { EatingLocationPage } from "@pos_self_order/app/pages/eating_location_page/eating_location_page";
import { patch } from "@web/core/utils/patch";

patch(EatingLocationPage.prototype, {
    setup() {
        super.setup(...arguments);
        const url = new URL(window.location.href);
        this.isTakeawayUrl = !url.searchParams.has("table_identifier");
    },

    /** One-tap enter for takeaway-only URL */
    enter() {
        this.selectLocation("out");
    },
});
