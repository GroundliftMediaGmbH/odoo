"""Non-invasive POS cash-count helper, using Odoo's native Cash In/Out.

Never alters native POS session posting or tip calculations.  Closing withdrawals
are posted as two ordinary POS cash-out transactions (daily surplus and tips).
All sums and authorization checks are recomputed on the server under a lock.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

# Values are cents, not floats. Used for the EUR register only.
EUR_DENOMINATIONS = (50000, 20000, 10000, 5000, 2000, 1000, 500,
                     200, 100, 50, 20, 10, 5, 2, 1)
MAX_PIECES_PER_DENOMINATION = 10000
# Differences larger than 1 euro must be clarified before *automatic* cash-out.
MAX_AUTO_CASH_DIFFERENCE_CENTS = 100


class PosSession(models.Model):
    _inherit = "pos.session"

    gl_cash_helper_done = fields.Boolean(string="Kassenzähl-Helfer: Entnahmen gebucht", copy=False, readonly=True)
    gl_cash_helper_before = fields.Monetary(string="Gezähltes Bargeld vor Entnahmen", copy=False, readonly=True)
    gl_cash_helper_after_plan = fields.Monetary(string="Soll-Bargeld nach Entnahmen", copy=False, readonly=True)
    gl_cash_helper_daily_out = fields.Monetary(string="Tagesüberschuss entnommen", copy=False, readonly=True)
    gl_cash_helper_tip_out = fields.Monetary(string="Trinkgeld bar ausgezahlt", copy=False, readonly=True)
    gl_cash_helper_card_tip = fields.Monetary(string="Sicher unbares Trinkgeld", copy=False, readonly=True)
    gl_cash_helper_details = fields.Json(string="Stückelzählung vor Entnahmen", copy=False, readonly=True)
    gl_cash_helper_snapshot = fields.Json(string="Entnahmeberechnung", copy=False, readonly=True)

    @api.model
    def _gl_helper_session(self, session_id, *, require_open=True):
        if isinstance(session_id, bool) or not isinstance(session_id, int):
            raise UserError(_("Ungültige Kassensitzung."))
        user = self.env.user
        if not user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Kein Zugriff auf die POS-Kasse."))
        session = self.browse(session_id).exists()
        if not session or session.company_id not in self.env.companies:
            raise AccessError(_("Kassensitzung nicht gefunden oder kein Firmenzugriff."))
        if (session.user_id != user and not user.has_group("point_of_sale.group_pos_manager")):
            raise AccessError(_("Nur der Sitzungsverantwortliche oder POS-Manager darf die Entnahme buchen."))
        if require_open and session.state not in ("opened", "closing_control"):
            raise UserError(_("Die Kassensitzung ist nicht geöffnet."))
        if not session.config_id.cash_control or not session.cash_journal_id:
            raise UserError(_("Für diese Kasse muss die Bargeldkontrolle aktiv sein."))
        return session

    @api.model
    def _gl_helper_money_details(self, values):
        if not isinstance(values, dict) or set(values) - set(str(v) for v in EUR_DENOMINATIONS):
            raise UserError(_("Ungültige Münzen-/Scheinstückelung."))
        normalized = {}
        total = 0
        for cents in EUR_DENOMINATIONS:
            quantity = values.get(str(cents), 0)
            if isinstance(quantity, bool):
                raise UserError(_("Stückzahl muss eine ganze Zahl sein."))
            try:
                number = Decimal(str(quantity))
            except (InvalidOperation, ValueError, TypeError):
                raise UserError(_("Stückzahl muss eine ganze Zahl sein."))
            if number != number.to_integral_value() or not (0 <= number <= MAX_PIECES_PER_DENOMINATION):
                raise UserError(_("Stückzahl außerhalb des erlaubten Bereichs (0–10000)."))
            count = int(number)
            normalized[str(cents)] = count
            total += cents * count
        return total, normalized

    def _gl_helper_tips(self):
        self.ensure_one()
        amounts = {"cash": 0, "noncash": 0, "mixed": 0, "total": 0}
        signature_rows = []
        orders = self.env["pos.order"].search([
            ("session_id", "=", self.id),
            ("state", "in", ("paid", "done", "invoiced")),
        ], order="id asc")
        tip_product = self.config_id.tip_product_id if "tip_product_id" in self.config_id._fields else False
        for order in orders:
            amount = order.tip_amount if "tip_amount" in order._fields else 0.0
            if not amount and tip_product:
                amount = sum(line.price_subtotal_incl for line in order.lines if line.product_id == tip_product)
            cents = int(round(float(amount or 0.0) * 100))
            payment_rows = sorted((payment.id, payment.payment_method_id.id,
                                   int(round(payment.amount * 100))) for payment in order.payment_ids)
            signature_rows.append((order.id, cents, payment_rows))
            if not cents:
                continue
            methods = order.payment_ids.mapped("payment_method_id")
            if methods and all(method.is_cash_count for method in methods):
                bucket = "cash"
            elif methods and all(not method.is_cash_count for method in methods):
                bucket = "noncash"
            else:
                bucket = "mixed"
            amounts[bucket] += cents
            amounts["total"] += cents
        if any(value < 0 for value in amounts.values()):
            raise UserError(_("Negatives Trinkgeld vorhanden. Bitte erst die Kassenbuchungen prüfen."))
        return amounts, signature_rows

    def _gl_helper_calculation(self, details):
        self.ensure_one()
        if self.currency_id.name != "EUR":
            raise UserError(_("Dieser Stückel-Helfer unterstützt derzeit ausschließlich EUR-Kassen."))
        counted, normalized = self._gl_helper_money_details(details)
        tips, signature_rows = self._gl_helper_tips()
        opening = int(round(self.cash_register_balance_start * 100))
        # Native Odoo closing amounts are session-local, never a sum of other
        # POS registers / terminal balances. Compare against the exact figure
        # the cashier sees in the native closing popup.
        closing = self.get_closing_control_data()
        cash_details = closing.get("default_cash_details") or {}
        if "amount" not in cash_details:
            raise UserError(_("Odoo konnte keinen Bargeld-Sollbestand für diese Kassensitzung liefern."))
        expected = int(round(float(cash_details["amount"]) * 100))
        discrepancy = counted - expected
        needs_reconciliation = abs(discrepancy) > MAX_AUTO_CASH_DIFFERENCE_CENTS
        # Mixed-payment tips are conservatively treated as cash. All tips,
        # including card tips, must ultimately be paid FROM THE SAME DRAWER;
        # don't inadvertently pay card tips twice (or create negative cash).
        tip_out = tips["total"]
        if tip_out > counted:
            raise UserError(_(
                "Gezähltes Bargeld reicht nicht aus, um das gesamte Trinkgeld bar auszuzahlen. "
                "Bitte die Zählung prüfen oder ohne automatische Entnahmen "
                "zur Odoo-Kassenprüfung wechseln."
            ))
        intended_daily_out = max(0, counted - opening - tips["cash"] - tips["mixed"])
        # Card-tip payouts must first be funded by available cash. When the
        # opening float is small (e.g. 0), cap daily cash-out accordingly.
        daily_out = min(intended_daily_out, counted - tip_out)
        daily_capped_by = intended_daily_out - daily_out
        remaining = counted - daily_out - tip_out
        shortage = max(0, opening - remaining)
        moves = sorted((l.id, int(round(l.amount * 100))) for l in self.sudo().statement_line_ids)
        identity = [self.id, opening, expected, normalized, signature_rows, moves]
        signature = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        return {
            "session_id": self.id,
            "session_name": self.name,
            "opening": opening / 100,
            "counted_before": counted / 100,
            "cash_tips": tips["cash"] / 100,
            "noncash_tips": tips["noncash"] / 100,
            "mixed_tips": tips["mixed"] / 100,
            "tip_total": tip_out / 100,
            "daily_out": daily_out / 100,
            "total_out": (daily_out + tip_out) / 100,
            "remaining": remaining / 100,
            "cash_shortfall": shortage / 100,
            "known_card_shortfall": tips["noncash"] / 100,
            "daily_capped_by_card_tips": daily_capped_by / 100,
            "unexplained_before": discrepancy / 100,
            "expected_before": expected / 100,
            "requires_reconciliation": needs_reconciliation,
            "cash_difference_limit": MAX_AUTO_CASH_DIFFERENCE_CENTS / 100,
            "signature": signature,
            "denominations": normalized,
        }

    @api.model
    def gl_cash_helper_preview(self, session_id, details):
        session = self._gl_helper_session(session_id)
        if session.gl_cash_helper_done:
            return {"already_posted": True, **session.gl_cash_helper_status(session_id)}
        return session._gl_helper_calculation(details)

    @api.model
    def gl_cash_helper_status(self, session_id):
        session = self._gl_helper_session(session_id, require_open=False)
        if not session.gl_cash_helper_done:
            return {"posted": False}
        state = dict(session.gl_cash_helper_snapshot or {})
        closing = session.get_closing_control_data()
        return {
            "posted": True,
            "plan": state,
            "expected_now": closing.get("default_cash_details", {}).get("amount", 0.0),
        }

    @api.model
    def gl_cash_helper_post(self, session_id, details, signature):
        session = self._gl_helper_session(session_id)
        if not isinstance(signature, str) or len(signature) != 64:
            raise UserError(_("Ungültige Entnahmevorschau."))
        if not self.env.user._has_cash_move_permission():
            raise AccessError(_("Keine Berechtigung für Cash Out. Bitte POS-Manager hinzuziehen."))
        # Serializes two devices attempting to book the same payout concurrently.
        self.env.cr.execute("SELECT id FROM pos_session WHERE id = %s FOR UPDATE", [session.id])
        session.invalidate_recordset()
        if session.gl_cash_helper_done:
            return {"already_posted": True, **session.gl_cash_helper_status(session_id)}
        if session.state not in ("opened", "closing_control"):
            raise UserError(_("Kassensitzung wurde inzwischen geschlossen."))
        plan = session._gl_helper_calculation(details)
        if signature != plan["signature"]:
            raise UserError(_("Seit der Vorschau haben sich Buchungen oder der Kassenbestand verändert. Bitte neu zählen und erneut berechnen."))
        if plan["requires_reconciliation"]:
            raise UserError(_(
                "Automatische Barentnahme gesperrt: Gezähltes Bargeld und Odoo-Soll "
                "weichen um mehr als 1,00 EUR ab. Bitte Zählung und "
                "Eröffnungsbestand prüfen. Danach neu berechnen oder die "
                "native Odoo-Kassenprüfung ohne automatische Entnahmen nutzen."
            ))
        daily_out = plan["daily_out"]
        tip_out = plan["tip_total"]
        partner_id = self.env.user.partner_id.id
        extras = {"translatedType": "Cash Out"}
        if daily_out:
            session.try_cash_in_out("out", daily_out, "Groundlift Tagesueberschuss / Abschöpfung", partner_id, extras)
        if tip_out:
            session.try_cash_in_out("out", tip_out, "Groundlift Trinkgeld bar ausgezahlt (inkl. Kartentrinkgeld)", partner_id, extras)
        session.write({
            "gl_cash_helper_done": True,
            "gl_cash_helper_before": plan["counted_before"],
            "gl_cash_helper_after_plan": plan["remaining"],
            "gl_cash_helper_daily_out": daily_out,
            "gl_cash_helper_tip_out": tip_out,
            "gl_cash_helper_card_tip": plan["noncash_tips"],
            "gl_cash_helper_details": plan["denominations"],
            "gl_cash_helper_snapshot": plan,
        })
        session.message_post(body=(
            "Groundlift Kassenzähl-Helfer: Gezähltes Bargeld VOR Entnahme: %.2f EUR; "
            "Tagesüberschuss Cash Out: %.2f EUR; Trinkgeld Cash Out: %.2f EUR "
            "(davon sicher unbar %.2f EUR; gemischt/unklar %.2f EUR); "
            "geplanter Rest: %.2f EUR; ursprünglich: %.2f EUR. "
            "Es handelt sich um echte Cash-Out-Buchungen, nicht um Kassendifferenzen."
        ) % (plan["counted_before"], daily_out, tip_out, plan["noncash_tips"],
             plan["mixed_tips"], plan["remaining"], plan["opening"]))
        # Use Odoo's actual closing-data computation: the cached, nonstored
        # cash_register_balance_end may not yet have invalidated after Cash Out.
        closing = session.get_closing_control_data()
        return {
            "posted": True,
            "plan": plan,
            "expected_now": closing.get("default_cash_details", {}).get("amount", 0.0),
        }
