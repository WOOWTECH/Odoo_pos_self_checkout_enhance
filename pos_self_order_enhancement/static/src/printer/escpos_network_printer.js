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
 * print jobs to the Odoo relay controller (/pos-escpos/print),
 * which forwards them to the local print proxy server.
 */
export class EscPosPrinter extends BasePrinter {
    setup({ printer_ip }) {
        super.setup(...arguments);
        this.printer_ip = printer_ip;
    }

    async sendPrintingJob(img) {
        const result = await rpc("/pos-escpos/print", {
            printer_ip: this.printer_ip,
            action: "print_receipt",
            receipt: img,
        });
        return { result: result.success };
    }

    openCashbox() {
        return rpc("/pos-escpos/print", {
            printer_ip: this.printer_ip,
            action: "cashbox",
        });
    }

    getActionError() {
        return {
            successful: false,
            message: {
                title: _t("Connection to print proxy failed"),
                body: _t(
                    "Please check that the ESC/POS print proxy server is running. " +
                    "Start it with: python tools/print_proxy.py"
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
                    "The print proxy received the job but could not print. " +
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
            return new EscPosPrinter({ printer_ip: config.escpos_printer_ip });
        }
        return super.create_printer(...arguments);
    },
});
