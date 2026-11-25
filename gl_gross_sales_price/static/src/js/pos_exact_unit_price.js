/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

/** Keep the already calculated net unit price for gross-managed products.
 * Never replace it with the catalog gross price: pricelists, discounts,
 * variants and fiscal positions must retain their normal Odoo semantics.
 * For other products, use the original Odoo implementation.
 */
patch(PosOrderline.prototype, {
    setUnitPrice(price) {
        const grossManaged = Boolean(
            this.product_id?.product_tmpl_id?.gl_gross_price_managed
        );
        if (!grossManaged) {
            return super.setUnitPrice(price);
        }
        const parsedPrice = typeof price === "number"
            ? price
            : Number.parseFloat(String(price ?? ""));
        this.price_unit = Number.isFinite(parsedPrice) ? parsedPrice : 0;
    },
});
