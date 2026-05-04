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
        // Record id is the primary lookup key for the backend controller.
        // IP is kept for back-compat and still used for direct local TCP.
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
});
