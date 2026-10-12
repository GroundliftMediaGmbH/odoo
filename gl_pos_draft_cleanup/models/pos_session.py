"""Safe, auditable cleanup of POS draft orders in *one* current session.

Never unlink POS orders; use Odoo's own action_pos_order_cancel().
"""

import logging
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)

# Do not touch drafts a cashier may still be editing/synchronizing.
MIN_IDLE_SECONDS = 60
MAX_CANDIDATES = 200


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _gl_draft_cleanup_session(self, session_id):
        user = self.env.user
        if not user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Keine Berechtigung zur POS-Entwurfsbereinigung."))
        if isinstance(session_id, bool) or not isinstance(session_id, int):
            raise UserError(_("Ungültige Kassensitzung."))

        session = self.browse(session_id).exists()
        if not session or session.state not in ("opened", "closing_control"):
            raise UserError(_("Die Kassensitzung ist nicht geöffnet."))
        if session.company_id not in self.env.companies:
            raise AccessError(_("Kein Zugriff auf diese Gesellschaft."))
        if session.config_id.current_session_id.id != session.id:
            raise UserError(_("Diese Kassensitzung ist nicht mehr die aktuelle Sitzung."))
        # A POS user cannot clean another operator's session unless they are a POS manager.
        if session.user_id != user and not user.has_group("point_of_sale.group_pos_manager"):
            raise AccessError(_("Nur der Sitzungsverantwortliche oder POS-Manager darf Entwürfe bereinigen."))
        return session

    @api.model
    def _gl_draft_cleanup_classify(self, order, cutoff):
        """Return category if an old draft is demonstrably non-revenue, else False."""
        if order.state != "draft" or not order.write_date or order.write_date > cutoff:
            return False
        if not float_is_zero(order.amount_total, precision_rounding=order.currency_id.rounding):
            return False
        if order.payment_ids or order.picking_ids or order.account_move or order.to_invoice:
            return False
        # Protect reserved future orders, even if zero and empty.
        if order.preset_time:
            return False
        if not order.lines:
            return "empty"

        # Cancellation entries must exactly offset matching positive lines.
        # A free product, discount-only order or two unrelated products does NOT qualify.
        quantities = defaultdict(float)
        positives = negatives = False
        for line in order.lines:
            if line.qty > 0:
                positives = True
            elif line.qty < 0:
                negatives = True
            else:
                return False
            tax_ids = tuple(sorted(line.tax_ids.ids)) if "tax_ids" in line._fields else ()
            key = (
                line.product_id.id,
                round(line.price_unit, 8),
                round(line.discount, 6),
                tax_ids,
            )
            quantities[key] += line.qty

        if positives and negatives and all(
            float_is_zero(qty, precision_digits=5) for qty in quantities.values()
        ):
            return "neutralized"
        return False

    @api.model
    def gl_preview_draft_cleanup(self, session_id):
        session = self._gl_draft_cleanup_session(session_id)
        cutoff = fields.Datetime.now() - timedelta(seconds=MIN_IDLE_SECONDS)
        orders = self.env["pos.order"].search([
            ("session_id", "=", session.id),
            ("state", "=", "draft"),
        ], order="id asc")

        candidates = []
        for order in orders:
            kind = self._gl_draft_cleanup_classify(order, cutoff)
            if kind:
                candidates.append({
                    "id": order.id,
                    "reference": order.pos_reference or order.name,
                    "kind": kind,
                    "version": order.write_date.isoformat(),
                })
        return {
            "session_name": session.name,
            "draft_count": len(orders),
            "candidates": candidates[:MAX_CANDIDATES],
            "skipped_count": len(orders) - len(candidates),
            "too_many": len(candidates) > MAX_CANDIDATES,
            "min_age_seconds": MIN_IDLE_SECONDS,
        }

    @api.model
    def gl_cancel_draft_cleanup(self, session_id, selected):
        session = self._gl_draft_cleanup_session(session_id)
        if not isinstance(selected, list) or not selected or len(selected) > MAX_CANDIDATES:
            raise UserError(_("Ungültige Auswahl. Bitte die Prüfung wiederholen."))

        try:
            requested = {item["id"]: item["version"] for item in selected}
            ids = sorted(requested)
            if len(requested) != len(selected) or any(
                isinstance(i, bool) or not isinstance(i, int) for i in ids
            ):
                raise ValueError("Invalid order IDs")
            if not all(isinstance(v, str) for v in requested.values()):
                raise ValueError("Invalid versions")
        except (KeyError, TypeError, ValueError):
            raise UserError(_("Ungültige Auswahl. Bitte die Prüfung wiederholen."))

        # Row locks prevent a concurrent cashier sync from changing these orders
        # between the final safety check and the standard Odoo cancellation.
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "SELECT id FROM pos_order WHERE id = ANY(%s) ORDER BY id FOR UPDATE NOWAIT",
                    (ids,),
                )
        except Exception as exc:
            # The savepoint keeps the transaction usable after a NOWAIT conflict.
            from psycopg2.errors import LockNotAvailable
            if isinstance(exc, LockNotAvailable):
                raise UserError(_("Ein Auftrag wird gerade bearbeitet. Bitte erneut versuchen.")) from exc
            raise

        orders = self.env["pos.order"].browse(ids).exists()
        orders.invalidate_recordset()
        if len(orders) != len(ids):
            raise UserError(_("Mindestens ein Auftrag existiert nicht mehr."))

        cutoff = fields.Datetime.now() - timedelta(seconds=MIN_IDLE_SECONDS)
        for order in orders:
            if order.session_id.id != session.id:
                raise UserError(_("Ein Auftrag gehört nicht zu dieser Kassensitzung."))
            kind = self._gl_draft_cleanup_classify(order, cutoff)
            if not kind or order.write_date.isoformat() != requested[order.id]:
                raise UserError(_(
                    "Auftrag %(ref)s wurde zwischenzeitlich geändert oder ist nicht mehr sicher stornierbar. "
                    "Bitte die Liste erneut laden.", ref=order.pos_reference or order.name
                ))

        # IMPORTANT: normal ORM cancellation, NOT unlink and NOT direct SQL UPDATE.
        orders.with_context(device_identifier=self.env.context.get("device_identifier", 0)).action_pos_order_cancel()
        if any(order.state != "cancel" for order in orders):
            raise UserError(_("Nicht alle Entwürfe konnten storniert werden."))
        _logger.warning(
            "Groundlift POS draft cleanup: user=%s session=%s canceled_orders=%s",
            self.env.uid, session.name, [(o.id, o.pos_reference) for o in orders]
        )
        return {"count": len(orders), "ids": orders.ids}
