/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

/**
 * Odoo 19 normally rounds every POS order-line unit price with the
 * "Product Price" decimal precision in PosOrderline.setUnitPrice().
 *
 * Groundlift gross-price-managed products intentionally keep an exact
 * tax-exclusive base (e.g. 3.80 / 1.19 = 3.193277310924...).
 * For those products only, preserve that value. All other products keep
 * Odoo's standard Product Price rounding.
 */
patch(PosOrderline.prototype, {
    setUnitPrice(price) {
        const ProductPrice = this.models["decimal.precision"].find(
            (dp) => dp.name === "Product Price"
        );

        let parsedPrice;
        if (typeof price === "number") {
            parsedPrice = price;
        } else {
            const candidate = Number.parseFloat(String(price ?? ""));
            parsedPrice = Number.isFinite(candidate) ? candidate : 0;
        }

        const grossManaged = Boolean(
            this.product_id?.product_tmpl_id?.gl_gross_price_managed
        );

        if (grossManaged || !ProductPrice) {
            this.price_unit = parsedPrice || 0;
            return;
        }

        this.price_unit = ProductPrice.round(parsedPrice || 0);
    },
});
