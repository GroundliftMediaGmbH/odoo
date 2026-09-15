/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.use_payment_terminal === "sumup" && this.isRefundOrder) {
            const refundedOrder = this.currentOrder.lines[0]?.refunded_orderline_id?.order_id;
            if (!refundedOrder) {
                this.notification.add(
                    _t("No refunded order was found for this SumUp refund."),
                    { type: "warning", sticky: false }
                );
                return false;
            }

            const usedTransactionIds = new Set(
                this.currentOrder.payment_ids
                    .map((line) => line.transaction_id)
                    .filter(Boolean)
            );

            const refundedPaymentLine = refundedOrder.payment_ids.find(
                (line) =>
                    line.payment_method_id.use_payment_terminal === "sumup" &&
                    line.transaction_id &&
                    !usedTransactionIds.has(line.transaction_id)
            );

            if (!refundedPaymentLine) {
                this.notification.add(
                    _t("There is no refundable SumUp transaction available on the original order."),
                    { type: "warning", sticky: false }
                );
                return false;
            }

            const result = await super.addNewPaymentLine(paymentMethod);
            if (!result) {
                return result;
            }

            const newPaymentLine = this.paymentLines.at(-1);
            newPaymentLine.transaction_id = refundedPaymentLine.transaction_id;
            return result;
        }

        return await super.addNewPaymentLine(paymentMethod);
    },
});
