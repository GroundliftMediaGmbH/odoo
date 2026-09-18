# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class InboxFilterBatch(models.Model):
    _name = "inbox.filter.batch"
    _description = "Inbox Filter Stapelverarbeitung"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, readonly=True)
    mode = fields.Selection([
        ("all", "Alle neu einsortieren"),
        ("errors", "Alle mit Fehler neu einsortieren"),
        ("automatic_errors", "Automatische Fehler-Nachprüfung"),
    ], required=True, readonly=True)
    state = fields.Selection([
        ("queued", "Vorbereitet"),
        ("running", "Läuft"),
        ("waiting", "Rate-Limit-Pause"),
        ("done", "Abgeschlossen"),
        ("cancelled", "Abgebrochen"),
    ], default="queued", required=True, readonly=True, index=True)
    user_id = fields.Many2one("res.users", string="Gestartet von", default=lambda self: self.env.user, readonly=True)
    started_at = fields.Datetime(string="Gestartet", readonly=True)
    finished_at = fields.Datetime(string="Beendet", readonly=True)
    next_run_at = fields.Datetime(string="Fortsetzen ab", readonly=True, index=True)
    total_count = fields.Integer(string="Gesamt", readonly=True)
    processed_count = fields.Integer(string="Bearbeitet", readonly=True)
    success_count = fields.Integer(string="Erfolgreich", readonly=True)
    error_count = fields.Integer(string="Fehler", readonly=True)
    skipped_count = fields.Integer(string="Übersprungen", readonly=True)
    progress = fields.Float(string="Fortschritt", compute="_compute_progress")
    current_history_id = fields.Many2one("inbox.filter.history", string="Aktueller Vorgang", readonly=True)
    last_message = fields.Char(string="Statusmeldung", readonly=True)
    line_ids = fields.One2many("inbox.filter.batch.line", "batch_id", string="Einträge", readonly=True)
    automatic = fields.Boolean(default=False, readonly=True)

    @api.depends("total_count", "processed_count")
    def _compute_progress(self):
        for rec in self:
            rec.progress = min(100.0, (100.0 * rec.processed_count / rec.total_count)) if rec.total_count else 100.0

    @api.model
    def _eligible_domain(self, mode):
        domain = [("perfect_recognized", "=", False), ("active", "=", True)]
        if mode in ("errors", "automatic_errors"):
            domain.append(("status", "=", "error"))
        return domain

    @api.model
    def create_batch(self, mode="all", automatic=False):
        if mode not in ("all", "errors", "automatic_errors"):
            mode = "all"
        # Nie zwei konkurrierende Massenläufe starten. Das verhindert doppelte API-Aufrufe
        # und doppelte Verschiebeaktionen, falls ein Button mehrfach geklickt wird.
        active_batch = self.sudo().search([
            ("state", "in", ["queued", "running", "waiting"]),
        ], order="create_date asc", limit=1)
        if active_batch:
            # Ein laufender "Alle"-Batch deckt auch den Fehler-Teilbestand ab.
            if active_batch.mode == "all" or active_batch.mode == mode or automatic:
                return active_batch
            # Startet der Benutzer bewusst "Alle", ersetzt dieser umfassendere Lauf einen
            # gerade wartenden reinen Fehler-Batch. Zwischen process_next_item-Aufrufen gibt es
            # keine offenen API-Requests, daher kann sauber umgeschaltet werden.
            if mode == "all" and active_batch.mode in ("errors", "automatic_errors"):
                active_batch.write({
                    "state": "cancelled",
                    "finished_at": fields.Datetime.now(),
                    "last_message": _("Durch einen neuen vollständigen Neu-Einsortierlauf ersetzt."),
                })
            else:
                return active_batch

        History = self.env["inbox.filter.history"].sudo()
        domain = self._eligible_domain(mode)
        if mode == "automatic_errors":
            now = fields.Datetime.now()
            domain += ["|", ("next_retry_at", "=", False), ("next_retry_at", "<=", now)]
        histories = History.search(domain, order="create_date asc, id asc")

        labels = dict(self._fields["mode"].selection)
        batch = self.sudo().create({
            "name": "%s – %s" % (labels.get(mode, mode), fields.Datetime.now()),
            "mode": mode,
            "automatic": bool(automatic),
            "total_count": len(histories),
            "last_message": _("%(count)s Datensätze vorbereitet.") % {"count": len(histories)},
        })
        if histories:
            Line = self.env["inbox.filter.batch.line"].sudo()
            # In moderaten Blöcken anlegen, damit auch große Historienbestände sauber starten.
            vals = [{"batch_id": batch.id, "history_id": h.id} for h in histories]
            for offset in range(0, len(vals), 500):
                Line.create(vals[offset:offset + 500])
        else:
            batch.write({
                "state": "done",
                "finished_at": fields.Datetime.now(),
                "last_message": _("Keine passenden Datensätze gefunden."),
            })
        return batch

    @api.model
    def action_start_batch(self, mode="all"):
        batch = self.create_batch(mode=mode, automatic=False)
        return {
            "type": "ir.actions.client",
            "tag": "inbox_filter.batch_progress",
            "name": _("Inbox Filter Fortschritt"),
            "params": {"batch_id": batch.id},
        }

    @api.model
    def get_progress(self, batch_id):
        batch = self.sudo().browse(int(batch_id or 0)).exists()
        if not batch:
            return {"exists": False}
        now = fields.Datetime.now()
        wait_seconds = 0
        if batch.next_run_at and batch.next_run_at > now:
            wait_seconds = max(0, int((batch.next_run_at - now).total_seconds()))
        return {
            "exists": True,
            "id": batch.id,
            "name": batch.name,
            "mode": batch.mode,
            "state": batch.state,
            "state_label": dict(batch._fields["state"].selection).get(batch.state, batch.state),
            "total_count": batch.total_count,
            "processed_count": batch.processed_count,
            "success_count": batch.success_count,
            "error_count": batch.error_count,
            "skipped_count": batch.skipped_count,
            "progress": round(batch.progress, 1),
            "last_message": batch.last_message or "",
            "current_history": batch.current_history_id.display_name if batch.current_history_id else "",
            "next_run_at": fields.Datetime.to_string(batch.next_run_at) if batch.next_run_at else False,
            "wait_seconds": wait_seconds,
            "done": batch.state in ("done", "cancelled"),
        }

    @api.model
    def process_next_item(self, batch_id):
        """Verarbeitet genau einen Eintrag.

        Der Browser kann diese Methode wiederholt aufrufen und so einen sichtbaren Live-Fortschritt
        erzeugen. Parallel sorgt ein Cron dafür, dass ein begonnener Job auch nach Schließen des
        Browserfensters weiterläuft. `FOR UPDATE SKIP LOCKED` verhindert Doppelverarbeitung.
        """
        batch = self.sudo().browse(int(batch_id or 0)).exists()
        if not batch or batch.state in ("done", "cancelled"):
            return self.get_progress(batch_id)

        now = fields.Datetime.now()
        if batch.next_run_at and batch.next_run_at > now:
            if batch.state != "waiting":
                batch.write({"state": "waiting"})
            return self.get_progress(batch.id)

        if not batch.started_at:
            batch.write({"started_at": now, "state": "running", "next_run_at": False})
        elif batch.state != "running":
            batch.write({"state": "running", "next_run_at": False})

        self.env.cr.execute("""
            SELECT id
              FROM inbox_filter_batch_line
             WHERE batch_id = %s
               AND state = 'pending'
             ORDER BY id
             LIMIT 1
             FOR UPDATE SKIP LOCKED
        """, [batch.id])
        row = self.env.cr.fetchone()
        if not row:
            self._finish_if_complete(batch)
            return self.get_progress(batch.id)

        line = self.env["inbox.filter.batch.line"].sudo().browse(row[0])
        history = line.history_id.sudo().exists()
        if not history:
            line.write({"state": "skipped", "message": _("Historien-Datensatz existiert nicht mehr.")})
            self._advance_counts(batch, skipped=1, message=line.message)
            self._finish_if_complete(batch)
            return self.get_progress(batch.id)

        if history.perfect_recognized:
            line.write({"state": "skipped", "message": _("Als perfekt erkannt markiert und daher übersprungen.")})
            self._advance_counts(batch, skipped=1, message=line.message)
            self._finish_if_complete(batch)
            return self.get_progress(batch.id)

        line.write({"state": "processing", "started_at": now, "attempt_count": line.attempt_count + 1})
        batch.write({"current_history_id": history.id, "last_message": _("Prüfe: %s") % history.display_name})

        service = self.env["inbox.filter.service"].sudo()
        try:
            service.reclassify_history_record(history)
            history.with_context(inbox_filter_allow_locked_write=True).write({
                "error_message": False,
                "retry_count": 0,
                "last_retry_at": now,
                "next_retry_at": False,
            })
            line.write({
                "state": "done",
                "finished_at": fields.Datetime.now(),
                "message": _("Erfolgreich neu einsortiert."),
            })
            self._advance_counts(batch, success=1, message=_("Erfolgreich: %s") % history.display_name)
        except Exception as exc:  # noqa: BLE001 - ein Eintrag darf den Stapel nie abbrechen
            # Rate-Limit-Ausnahmen sind absichtlich transient: derselbe Eintrag bleibt pending
            # und wird nach dem vom Service errechneten Reset erneut versucht.
            if getattr(exc, "inbox_filter_rate_limit", False):
                delay = max(1, int(getattr(exc, "retry_seconds", 5) or 5))
                retry_at = fields.Datetime.now() + timedelta(seconds=delay)
                line.write({
                    "state": "pending",
                    "message": str(exc),
                })
                batch.write({
                    "state": "waiting",
                    "next_run_at": retry_at,
                    "last_message": _("OpenAI Rate-Limit-Pause – Fortsetzung automatisch in ca. %(seconds)s Sekunden.") % {"seconds": delay},
                })
                return self.get_progress(batch.id)

            _logger.exception("Inbox Filter batch reclassification failed for history %s", history.id)
            retry_count = (history.retry_count or 0) + 1
            retry_minutes = min(24 * 60, 5 * (2 ** min(retry_count - 1, 8)))
            retry_at = fields.Datetime.now() + timedelta(minutes=retry_minutes)
            try:
                history.with_context(inbox_filter_allow_locked_write=True).write({
                    "status": "error",
                    "error_message": str(exc),
                    "retry_count": retry_count,
                    "last_retry_at": fields.Datetime.now(),
                    "next_retry_at": retry_at,
                })
                history.message_post(body=_("Neu-Einsortierung fehlgeschlagen; automatische erneute Prüfung ist vorgemerkt: %s") % str(exc))
            except Exception:  # noqa: BLE001
                _logger.exception("Could not update retry metadata for history %s", history.id)
            line.write({
                "state": "error",
                "finished_at": fields.Datetime.now(),
                "message": str(exc)[:1000],
            })
            self._advance_counts(batch, error=1, message=_("Fehler bei %s – wird später automatisch erneut geprüft.") % history.display_name)

        self._finish_if_complete(batch)
        return self.get_progress(batch.id)

    def _advance_counts(self, batch, success=0, error=0, skipped=0, message=None):
        batch.sudo().write({
            "processed_count": batch.processed_count + success + error + skipped,
            "success_count": batch.success_count + success,
            "error_count": batch.error_count + error,
            "skipped_count": batch.skipped_count + skipped,
            "last_message": message or batch.last_message,
            "current_history_id": False,
        })

    def _finish_if_complete(self, batch):
        pending = self.env["inbox.filter.batch.line"].sudo().search_count([
            ("batch_id", "=", batch.id),
            ("state", "in", ["pending", "processing"]),
        ])
        if not pending:
            batch.sudo().write({
                "state": "done",
                "finished_at": fields.Datetime.now(),
                "next_run_at": False,
                "current_history_id": False,
                "last_message": _("Abgeschlossen: %(ok)s erfolgreich, %(errors)s Fehler, %(skipped)s übersprungen.") % {
                    "ok": batch.success_count,
                    "errors": batch.error_count,
                    "skipped": batch.skipped_count,
                },
            })

    @api.model
    def _cron_process_batches(self):
        now = fields.Datetime.now()
        # Falls ein Odoo-Worker während eines API-Aufrufs beendet wurde, darf die Zeile nicht
        # dauerhaft auf "processing" hängen bleiben. Nach 10 Minuten wird sie wieder freigegeben.
        stale_before = now - timedelta(minutes=10)
        stale_lines = self.env["inbox.filter.batch.line"].sudo().search([
            ("state", "=", "processing"),
            ("started_at", "<", stale_before),
        ])
        if stale_lines:
            stale_lines.write({"state": "pending", "message": _("Nach Worker-Abbruch automatisch erneut freigegeben.")})
        batches = self.sudo().search([
            ("state", "in", ["queued", "running", "waiting"]),
            "|", ("next_run_at", "=", False), ("next_run_at", "<=", now),
        ], order="create_date asc", limit=5)
        for batch in batches:
            try:
                self.process_next_item(batch.id)
            except Exception:  # noqa: BLE001
                _logger.exception("Inbox Filter cron could not process batch %s", batch.id)
        return True

    @api.model
    def _cron_create_retry_batch(self):
        settings = self.env["inbox.filter.settings"].sudo().get_singleton()
        if not settings.error_retry_enabled:
            return True
        # Läuft bereits ein Job, werden keine konkurrierenden Wiederholungen erzeugt.
        if self.sudo().search_count([("state", "in", ["queued", "running", "waiting"])]) > 0:
            return True
        now = fields.Datetime.now()
        History = self.env["inbox.filter.history"].sudo()
        due = History.search_count([
            ("status", "=", "error"),
            ("perfect_recognized", "=", False),
            ("active", "=", True),
            "|", ("next_retry_at", "=", False), ("next_retry_at", "<=", now),
        ])
        if due:
            batch = self.create_batch(mode="automatic_errors", automatic=True)
            if batch and batch.state != "done":
                self.process_next_item(batch.id)
        return True


class InboxFilterBatchLine(models.Model):
    _name = "inbox.filter.batch.line"
    _description = "Inbox Filter Stapelzeile"
    _order = "id asc"

    batch_id = fields.Many2one("inbox.filter.batch", required=True, ondelete="cascade", index=True)
    history_id = fields.Many2one("inbox.filter.history", required=True, ondelete="cascade", index=True)
    state = fields.Selection([
        ("pending", "Wartet"),
        ("processing", "Wird verarbeitet"),
        ("done", "Erfolgreich"),
        ("error", "Fehler"),
        ("skipped", "Übersprungen"),
    ], default="pending", required=True, index=True)
    attempt_count = fields.Integer(default=0)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    message = fields.Text(readonly=True)
