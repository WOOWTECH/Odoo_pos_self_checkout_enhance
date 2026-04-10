/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * Taiwan E-Invoice receipt component for ESC/POS thermal printing.
 *
 * Renders a MOF-compliant 統一發票 with QR codes, barcode, ROC date,
 * items table, and tax breakdown.
 *
 * Props:
 *   order       - pos.order record
 *   invoiceData - { invoice_no, random_code, qrcode_left, qrcode_right, pos_barcode }
 *   sellerTaxId - seller's 統一編號
 */
export class TwInvoiceReceipt extends Component {
    static template = "pos_self_order_enhancement.TwInvoiceReceipt";
    static props = {
        order: Object,
        invoiceData: Object,
        sellerTaxId: { type: String, optional: true },
    };

    get rocYear() {
        return new Date().getFullYear() - 1911;
    }

    get invoicePeriod() {
        const now = new Date();
        const month = now.getMonth() + 1; // 1-12
        // Taiwan invoice periods are bimonthly: 01-02, 03-04, 05-06, etc.
        const startMonth = month % 2 === 0 ? month - 1 : month;
        const endMonth = startMonth + 1;
        const pad = (n) => String(n).padStart(2, "0");
        return `${this.rocYear}年${pad(startMonth)}-${pad(endMonth)}月`;
    }

    get formattedInvoiceNo() {
        const no = this.props.invoiceData.invoice_no || "";
        // Format: AB-12345678
        if (no.length === 10) {
            return `${no.slice(0, 2)}-${no.slice(2)}`;
        }
        return no;
    }

    get rocDateTime() {
        const now = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        return `${this.rocYear}/${pad(now.getMonth() + 1)}/${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    }

    get orderLines() {
        const order = this.props.order;
        return order.lines || order.orderlines || [];
    }

    get totalAmount() {
        return Math.round(this.props.order.amount_total || 0);
    }

    get taxAmount() {
        return Math.round(this.props.order.amount_tax || 0);
    }

    get salesAmount() {
        return this.totalAmount - this.taxAmount;
    }

    get qrLeftUrl() {
        const data = this.props.invoiceData.qrcode_left;
        if (!data) return "";
        return `/report/barcode/?barcode_type=QR&value=${encodeURIComponent(data)}&width=240&height=240`;
    }

    get qrRightUrl() {
        const data = this.props.invoiceData.qrcode_right;
        if (!data) return "";
        return `/report/barcode/?barcode_type=QR&value=${encodeURIComponent(data)}&width=240&height=240`;
    }

    get barcodeUrl() {
        const data = this.props.invoiceData.pos_barcode;
        if (!data) return "";
        return `/report/barcode/?barcode_type=Code39&value=${encodeURIComponent(data)}&width=520&height=80`;
    }
}
