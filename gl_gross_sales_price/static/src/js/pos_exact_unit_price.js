/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

/**
 * Odoo 19 rounds every POS unit price to the configured "Product Price"
 * decimal precision in PosOrderline.setUnitPrice(). With the common setting
 * of two decimals, a tax-exclusive base price such as 3.80 / 1.19 =
 * 3.193277... is converted to 3.19 inside the POS. Two such products then
 * produce 7.59 instead of the intended 7.60 gross total.
 *
 * We only bypass that rounding when the product template itself contains a
 * sub-precision list_price. This keeps standard Odoo behaviour for ordinary
 * two-decimal products and manual POS prices, while preserving the exact net
 * base created by the Groundlift gross-price field.
 */
patch(PosOrderline.prototype, {
    setUnitPrice(price) {
        const ProductPrice = this.models["decimal.precision"].find(
            (dp) => dp.name === "Product Price"
        );
        const parsedPrice = !isNaN(price)
            ? Number(price)
            : isNaN(Number.parseFloat(price))
            ? 0
            : Number.parseFloat(String(price));
        const value = parsedPrice || 0;

        const template = this.product_id?.product_tmpl_id;
        const basePrice = template?.list_price;
        const roundedBasePrice =
            typeof basePrice === "number" && ProductPrice
                ? ProductPrice.round(basePrice)
                : basePrice;
        const hasSubPrecisionBase =
            typeof basePrice === "number" &&
            typeof roundedBasePrice === "number" &&
            Math.abs(basePrice - roundedBasePrice) > 1e-9;

        this.price_unit = hasSubPrecisionBase || !ProductPrice
            ? value
            : ProductPrice.round(value);
    },
});
