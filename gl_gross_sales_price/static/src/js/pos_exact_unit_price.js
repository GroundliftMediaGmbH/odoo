/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { roundPrecision } from "@web/core/utils/numbers";
import { accountTaxHelpers } from "@account/helpers/account_tax";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { ProductTemplateAccounting } from "@point_of_sale/app/models/accounting/product_template_accounting";

const GL_GROSS_KEY = "gl_pos_fixed_gross_v1";
const EPSILON = 0.00001;

function simpleVat(taxes) {
    if (taxes?.length !== 1) return null;
    const tax = taxes[0];
    return tax.amount_type === "percent" && !tax.price_include && tax.amount >= 0 &&
        !tax.include_base_amount && !tax.has_negative_factor ? tax : null;
}

function matchesMaster(template, price, taxes, currency) {
    const tax = simpleVat(taxes);
    return Boolean(template?.gl_gross_price_managed && tax && currency &&
        Number.isFinite(template.gross_list_price) &&
        (!template.currency_id || template.currency_id.id === currency.id) &&
        Math.abs(price * (1 + tax.amount / 100) - template.gross_list_price) <= EPSILON);
}

function fixedGrossUnit(line) {
    if (line.computation_key !== GL_GROSS_KEY || line.special_mode || line.special_type ||
        line.filter_tax_function || (line.manual_tax_amounts && Object.keys(line.manual_tax_amounts).length) ||
        line.manual_total_excluded_currency != null || line.manual_total_excluded != null) return null;
    const tax = simpleVat(line.tax_ids);
    if (!tax) return null;
    const raw = line.price_unit * (1 + tax.amount / 100);
    const gross = roundPrecision(raw, line.currency_id.rounding);
    return Math.abs(raw - gross) <= EPSILON ? gross : null;
}

// Retain native rounding for other products. A computation_key is an Odoo
// supported extra_tax_data value which survives POS sync and invoice export.
patch(PosOrderline.prototype, {
    setUnitPrice(price) {
        const template = this.product_id?.product_tmpl_id;
        const oldPrice = this.price_unit;
        const previous = this.extra_tax_data || {};
        const existingKey = previous.computation_key;
        if (template?.gl_gross_price_managed || existingKey === GL_GROSS_KEY) {
            const candidate = typeof price === "number" ? price : Number.parseFloat(String(price ?? ""));
            this.price_unit = Number.isFinite(candidate) ? candidate : 0;
        } else {
            super.setUnitPrice(price);
        }
        // Don't replace native manual tax data (combos, special discounts).
        if (Object.keys(previous).some((key) => key !== "computation_key") ||
            (existingKey && existingKey !== GL_GROSS_KEY)) return;
        const refund = this.refunded_orderline_id;
        const inherited = refund?.extra_tax_data?.computation_key === GL_GROSS_KEY &&
            Math.abs(this.price_unit - refund.price_unit) <= EPSILON;
        const unchanged = existingKey === GL_GROSS_KEY && Math.abs(this.price_unit - oldPrice) <= EPSILON;
        const ordinary = !refund && !this.combo_parent_id && !this.combo_item_id &&
            template?.type !== "combo" && !this.price_extra &&
            matchesMaster(template, this.price_unit, this.product_id?.taxes_id || template?.taxes_id, this.currency);
        const nextKey = inherited || unchanged || ordinary ? GL_GROSS_KEY : null;
        if ((existingKey || null) !== nextKey) {
            this.extra_tax_data = nextKey ? { computation_key: nextKey } : {};
            this.order_id?.triggerRecomputeAllPrices?.();
        }
    },
});

// Also correct the product tile before adding it to an order.
patch(ProductTemplateAccounting.prototype, {
    getBaseLine(opts = {}) {
        const line = super.getBaseLine(opts);
        const template = this.product_tmpl_id || this;
        if (!line.computation_key && !line.special_mode &&
            matchesMaster(template, line.price_unit, line.tax_ids, line.currency_id)) {
            line.computation_key = GL_GROSS_KEY;
        }
        return line;
    },
});

// Mirror the Python tax helper. Do not rewrite UI totals or payment amounts.
// Instead, feed the native tax engine the gross amount and preserve its VAT
// allocation. Only explicitly marked simple VAT lines are affected.
patch(accountTaxHelpers, {
    add_tax_details_in_base_line(line, company, opts = {}) {
        const gross = fixedGrossUnit(line);
        if (gross === null) {
            delete line._gl_fixed_gross_computed;
            return super.add_tax_details_in_base_line(line, company, opts);
        }
        const work = { ...line, price_unit: gross, special_mode: "total_included" };
        const result = super.add_tax_details_in_base_line(work, company, opts);
        line.tax_details = work.tax_details;
        line._gl_fixed_gross_computed = true;
        return result;
    },
    round_base_lines_tax_details(lines, company) {
        const result = super.round_base_lines_tax_details(lines, company);
        for (const line of lines) {
            if (!line._gl_fixed_gross_computed || fixedGrossUnit(line) === null) continue;
            const details = line.tax_details;
            if (details.taxes_data.length !== 1) continue;
            const tax = details.taxes_data[0];
            for (const [suffix, currency] of [["_currency", line.currency_id], ["", company.currency_id]]) {
                const gross = roundPrecision(details[`raw_total_included${suffix}`], currency.rounding);
                const net = roundPrecision(gross - tax[`tax_amount${suffix}`], currency.rounding);
                details[`total_excluded${suffix}`] = net;
                details[`total_included${suffix}`] = gross;
                details[`delta_total_excluded${suffix}`] = 0;
                tax[`base_amount${suffix}`] = net;
            }
        }
        return result;
    },
});
