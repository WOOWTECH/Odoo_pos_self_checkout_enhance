/** @odoo-module **/

/**
 * Return the printer instance designated to print 電子統一發票 for this POS.
 *
 * Preference order:
 *   1. pos.config.einvoice_printer_id (explicit admin choice on POS config)
 *   2. first printer whose config.printer_type === "network_escpos" (legacy)
 *
 * Returns undefined when no suitable printer exists.
 */
export function selectEinvoicePrinter(pos) {
    const printers = pos?.unwatched?.printers || [];
    const configured = pos?.config?.einvoice_printer_id;
    // Many2one on the frontend may arrive as a related record object (has .id)
    // or as a raw id number, depending on how the data layer hydrates it.
    const configuredId = configured?.id ?? (typeof configured === "number" ? configured : null);
    if (configuredId) {
        const match = printers.find((p) => p.config?.id === configuredId);
        if (match) return match;
    }
    return printers.find((p) => p.config?.printer_type === "network_escpos");
}
