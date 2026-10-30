/** @odoo-module **/

import { BasePrinter } from "@point_of_sale/app/printer/base_printer";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

/**
 * Printer class for generic ESC/POS network printers.
 *
 * Instead of communicating directly with the printer (which would
 * require CORS and mixed-content workarounds), this class sends
 * print jobs to the Odoo controller (/pos-escpos/print), which
 * prints them in-process via a TCP socket on port 9100. No external
 * proxy process is required.
 */
export class EscPosPrinter extends BasePrinter {
    setup({ printer_id, printer_ip }) {
        super.setup(...arguments);
        this.printer_id = printer_id;
        this.printer_ip = printer_ip;
    }

    async sendPrintingJob(img) {
        const result = await rpc("/pos-escpos/print", {
            printer_id: this.printer_id,
            printer_ip: this.printer_ip,
            action: "print_receipt",
            receipt: img,
        });
        return { result: result.success };
    }

    openCashbox() {
        return rpc("/pos-escpos/print", {
            printer_id: this.printer_id,
            printer_ip: this.printer_ip,
            action: "cashbox",
        });
    }

    getActionError() {
        return {
            successful: false,
            message: {
                title: _t("Connection to printer failed"),
                body: _t(
                    "Could not reach the printer. Check that it is powered on, " +
                    "connected to the network, and that the IP address is correct."
                ),
            },
        };
    }

    getResultsError() {
        return {
            successful: false,
            message: {
                title: _t("Printing failed"),
                body: _t(
                    "The printer received the job but could not print. " +
                    "Please check that the printer is powered on, connected to the network, " +
                    "and has paper loaded."
                ),
            },
        };
    }
}

patch(PosStore.prototype, {
    create_printer(config) {
        if (config.printer_type === "network_escpos") {
            return new EscPosPrinter({
                printer_id: config.id,
                printer_ip: config.escpos_printer_ip,
            });
        }
        return super.create_printer(...arguments);
    },

    /**
     * For network_escpos printers: use server-side Pillow rendering
     * instead of browser html-to-image. This avoids blank receipts
     * caused by CJK font embedding failure in SVG foreignObject.
     */
    async printReceipts(order, printer, title, lines, fullReceipt = false, diningModeUpdate) {
        if (
            printer instanceof EscPosPrinter &&
            order &&
            typeof order.id === "number" &&
            lines &&
            lines.length > 0
        ) {
            try {
                const result = await rpc("/pos-escpos/print-order", {
                    order_id: order.id,
                    printer_id: printer.printer_id,
                    title: title || "New",
                    lines: lines.map((l) => ({
                        name: l.name || l.basic_name || "",
                        quantity: l.quantity || 0,
                        note: l.note || "",
                    })),
                });
                if (result && result.success) {
                    return true;
                }
                console.warn("[escpos] server-side print returned failure, trying browser fallback");
            } catch (e) {
                console.warn("[escpos] server-side print RPC failed, trying browser fallback:", e);
            }
        }
        return super.printReceipts(order, printer, title, lines, fullReceipt, diningModeUpdate);
    },
});
