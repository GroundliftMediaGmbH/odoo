/** @odoo-module */
import { register_payment_method } from "@point_of_sale/app/services/pos_store";
import { PaymentSumup } from "../../app/sumup_payment";

register_payment_method("sumup", PaymentSumup);