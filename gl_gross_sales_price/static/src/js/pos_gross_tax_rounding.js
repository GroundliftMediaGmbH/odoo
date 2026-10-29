/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { accountTaxHelpers } from "@account/helpers/account_tax";
import { PosOrderAccounting } from "@point_of_sale/app/models/accounting/pos_order_accounting";

/**
 * Odoo 19 computes all POS base lines together and then performs a global
 * tax-cent redistribution in round_base_lines_tax_details().
 *
 * For products whose exact net price was derived from a fixed gross price
 * (Groundlift's gl_gross_price_managed), that can change the customer-facing
 * basket by one cent. Example: visible gross lines sum to 56.00 EUR while the
 * global 7%/19% tax redistribution yields 55.99 EUR.
 *
 * We keep Odoo's normal behaviour for every other line. Only managed lines
 * explicitly use round_per_line when their raw tax details are created.
 */
patch(PosOrderAccounting.prototype, {
    _computeAllPrices(opts = {}) {
        const currency = this.currency;
        const lines = opts.lines || this.lines;
        const documentSign = this.isRefund ? -1 : 1;
        const company = this.company;

        const baseLines = lines.map((line) => {
            const baseLine = line.getBaseLine({
                quantity: line.qty,
                price_unit: line.price_unit,
                ...(opts.baseLineOpts || {}),
            });

            baseLine._gl_gross_price_managed = Boolean(
                line.product_id?.product_tmpl_id?.gl_gross_price_managed
            );
            return baseLine;
        });

        // Core Odoo normally calls add_tax_details_in_base_lines(baseLines, company).
        // We call the single-line helper so the rounding method can be selected
        // independently for each managed line.
        for (const baseLine of baseLines) {
            accountTaxHelpers.add_tax_details_in_base_line(baseLine, company, {
                rounding_method: baseLine._gl_gross_price_managed
                    ? "round_per_line"
                    : company.tax_calculation_rounding_method,
            });
        }

        accountTaxHelpers.round_base_lines_tax_details(baseLines, company);

        const cashRounding =
            this.config.cash_rounding && this.config.rounding_method
                ? this.config.rounding_method
                : null;

        const data = accountTaxHelpers.get_tax_totals_summary(
            baseLines,
            currency,
            company,
            { cash_rounding: cashRounding }
        );

        const total =
            data.total_amount_currency -
            (data.cash_rounding_base_amount_currency || 0.0);

        data.order_sign = documentSign;
        data.total_amount_no_rounding = total;

        const baseLineByLineUuids = baseLines.reduce((acc, line) => {
            acc[line.record.uuid] = line;
            return acc;
        }, {});

        return {
            taxDetails: data,
            baseLines,
            baseLineByLineUuids,
        };
    },
});
