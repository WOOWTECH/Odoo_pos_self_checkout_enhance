/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";
import { loadAllImages } from "@point_of_sale/utils";
import { selectEinvoicePrinter } from "@pos_einvoice_bridge/printer/select_einvoice_printer";

patch(PosStore.prototype, {
    async initServerData() {
        const result = await super.initServerData(...arguments);
        this._einvoicePrintedOrders = new Set();
        this.data.connectWebSocket("EINVOICE_PRINT", async (data) => {
            await this._onEinvoicePrint(data);
        });
        return result;
    },

    async _onEinvoicePrint(data) {
        if (!data.order_id) return;
        if (this._einvoicePrintedOrders.has(data.order_id)) return;
        this._einvoicePrintedOrders.add(data.order_id);

        // Fetch order so it's in local store
        try {
            await this.data.read("pos.order", [data.order_id]);
        } catch (e) { /* may already be loaded */ }

        // Find the designated e-invoice printer
        const escposPrinter = selectEinvoicePrinter(this);
        if (!escposPrinter) return;

        // Get server-rendered invoice HTML
        try {
            const result = await this.data.call(
                "pos.order",
                "get_einvoice_print_html",
                [[data.order_id]]
            );
            if (!result?.html) return;

            // Render in DOM off-screen and print via ESC/POS
            const container = document.createElement("div");
            container.innerHTML = result.html;
            container.style.position = "fixed";
            container.style.left = "-9999px";
            document.body.appendChild(container);

            const el = container.querySelector(".invoiceContainer") || container.firstElementChild;
            await loadAllImages(el);
            try {
                await escposPrinter.printReceipt(el);
            } catch (printErr) {
                console.warn("EINVOICE_PRINT: printer error (non-fatal):", printErr);
            }
            container.remove();
        } catch (e) {
            console.warn("EINVOICE_PRINT: failed to render/print:", e);
        }
    },
});
