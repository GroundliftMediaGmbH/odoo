import calendar
import logging
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)


class CleverReachNewsletterConfig(models.Model):
    _inherit = "gl.cleverreach.newsletter.config"

    event_participant_group_name = fields.Char(
        string="Event-Teilnehmer: CleverReach-Liste",
        default="Newsletter_allgemein",
        required=True,
        help=(
            "In diese CleverReach-Empfängerliste werden Event-Teilnehmer mit "
            "aktivem Newsletter-Haken übertragen."
        ),
    )
    event_participant_bulk_imported_at = fields.Datetime(
        string="Bestandsimport abgeschlossen am",
        readonly=True,
        copy=False,
    )
    event_participant_bulk_imported_count = fields.Integer(
        string="Bestandsimport: neu übertragen",
        readonly=True,
        copy=False,
    )
    event_participant_bulk_existing_count = fields.Integer(
        string="Bestandsimport: bereits vorhanden",
        readonly=True,
        copy=False,
    )
    event_participant_bulk_skipped_count = fields.Integer(
        string="Bestandsimport: lokal übersprungen",
        readonly=True,
        copy=False,
    )
    event_participant_bulk_last_message = fields.Text(
        string="Bestandsimport: letzter Status",
        readonly=True,
        copy=False,
    )
    event_participant_name_attributes_ready = fields.Boolean(
        string="CleverReach Namensfelder geprüft",
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Target list / receiver helpers
    # ------------------------------------------------------------------
    def _gl_event_get_target_group(self, sync_if_missing=False, raise_if_missing=True):
        self.ensure_one()
        target_name = (self.event_participant_group_name or "Newsletter_allgemein").strip()

        # Fast path: the globally selected newsletter list is already the target.
        if (
            self.recipient_group_id
            and (self.recipient_group_id.name or "").strip().casefold()
            == target_name.casefold()
        ):
            return self.recipient_group_id

        group = self.env["gl.cleverreach.group"].sudo().search(
            [
                ("config_id", "=", self.id),
                ("name", "=ilike", target_name),
                ("active", "=", True),
            ],
            limit=1,
        )
        if not group and sync_if_missing:
            self.action_sync_groups()
            group = self.env["gl.cleverreach.group"].sudo().search(
                [
                    ("config_id", "=", self.id),
                    ("name", "=ilike", target_name),
                    ("active", "=", True),
                ],
                limit=1,
            )

        if not group and raise_if_missing:
            raise UserError(
                _(
                    "Die CleverReach-Empfängerliste '%s' wurde in dieser "
                    "Konfiguration nicht gefunden. Bitte zuerst 'Listen "
                    "importieren' ausführen und den Listennamen prüfen."
                )
                % target_name
            )
        return group

    @staticmethod
    def _gl_event_normalize_email(value):
        normalized = email_normalize(value or "")
        return (normalized or "").strip().lower()

    @staticmethod
    def _gl_event_split_name(name):
        clean = " ".join((name or "").split()).strip()
        if not clean:
            return "", ""
        if "," in clean:
            last, first = clean.split(",", 1)
            return first.strip(), last.strip()
        if " " not in clean:
            return clean, ""
        first, last = clean.split(" ", 1)
        return first.strip(), last.strip()

    @staticmethod
    def _gl_event_unix_timestamp(value=None):
        dt = fields.Datetime.to_datetime(value) if value else fields.Datetime.now()
        return int(calendar.timegm(dt.utctimetuple()))

    def _gl_event_ensure_name_attributes(self):
        """Ensure the two global CleverReach fields used by this module exist."""
        self.ensure_one()
        if self.event_participant_name_attributes_ready:
            return True

        data = self._api("GET", "/attributes")
        items = data
        if isinstance(data, dict):
            items = data.get("data") or data.get("items") or data.get("attributes") or []
        if not isinstance(items, list):
            raise UserError(_("Unerwartete CleverReach-Attribut-Antwort: %s") % data)

        existing = {
            str(item.get("name") or "").strip().casefold()
            for item in items
            if isinstance(item, dict)
        }
        for attribute_name in ("firstname", "lastname"):
            if attribute_name.casefold() not in existing:
                self._api(
                    "POST",
                    "/attributes",
                    payload={"name": attribute_name, "type": "text"},
                )
        self.sudo().write({"event_participant_name_attributes_ready": True})
        return True

    def _gl_event_receiver_payload(self, registration, source=None, activated_at=None):
        self.ensure_one()
        email = self._gl_event_normalize_email(registration.email)
        if not email:
            raise UserError(_("Keine gültige E-Mail-Adresse vorhanden."))
        firstname, lastname = self._gl_event_split_name(registration.name)
        registered_at = registration.create_date or fields.Datetime.now()
        activation_time = activated_at or fields.Datetime.now()
        return {
            "email": email,
            "registered": str(self._gl_event_unix_timestamp(registered_at)),
            "activated": str(self._gl_event_unix_timestamp(activation_time)),
            "source": source or "Odoo Event Newsletter-Opt-in",
            "global_attributes": {
                "firstname": firstname,
                "lastname": lastname,
            },
        }

    def _gl_event_receiver_exists(self, group, email):
        self.ensure_one()
        normalized = self._gl_event_normalize_email(email)
        if not normalized:
            return False
        path = "/groups/%s/receivers/%s" % (
            group.external_id,
            quote(normalized, safe=""),
        )
        try:
            self._api("GET", path)
            return True
        except UserError as exc:
            text = str(exc).lower()
            if "404" in text or "not found" in text:
                return False
            raise

    def _gl_event_sync_registration(self, registration, group=None):
        """Insert one opted-in attendee, but never update an existing receiver."""
        self.ensure_one()
        registration.ensure_one()
        group = group or self._gl_event_get_target_group()
        email = self._gl_event_normalize_email(registration.email)
        if not email:
            return "invalid_email", _("Keine gültige E-Mail-Adresse vorhanden.")

        # Explicit duplicate test before every live upload.
        if self._gl_event_receiver_exists(group, email):
            return "exists", _("Empfänger ist in CleverReach bereits vorhanden.")

        self._gl_event_ensure_name_attributes()
        payload = self._gl_event_receiver_payload(
            registration,
            source="Odoo Event Newsletter-Opt-in",
            activated_at=registration.gl_cr_newsletter_optin_at or fields.Datetime.now(),
        )
        self._api(
            "POST",
            "/groups/%s/receivers" % group.external_id,
            payload=payload,
        )
        return "synced", _("Empfänger wurde zu CleverReach übertragen.")

    @api.model
    def _gl_event_find_live_config_and_group(self):
        Config = self.sudo()
        configs = Config.search([("active", "=", True)], order="id")
        for config in configs:
            group = config._gl_event_get_target_group(
                sync_if_missing=False, raise_if_missing=False
            )
            if group:
                return config, group
        return Config.browse([]), self.env["gl.cleverreach.group"].browse([])

    # ------------------------------------------------------------------
    # Historical one-time import
    # ------------------------------------------------------------------
    def _gl_event_fetch_existing_emails(self, group):
        """Load all group receiver e-mails once for a proper pre-import dedupe."""
        self.ensure_one()
        result = set()
        page = 0
        page_size = 5000

        while True:
            data = self._api(
                "GET",
                "/groups/%s/receivers" % group.external_id,
                params={
                    "page": page,
                    "pagesize": page_size,
                    "type": "all",
                    "detail": 0,
                },
            )
            items = data
            if isinstance(data, dict):
                items = (
                    data.get("data")
                    or data.get("items")
                    or data.get("receivers")
                    or []
                )
            if not isinstance(items, list):
                raise UserError(
                    _("Unerwartete CleverReach-Empfänger-Antwort: %s") % data
                )

            for item in items:
                if not isinstance(item, dict):
                    continue
                email = self._gl_event_normalize_email(item.get("email"))
                if email:
                    result.add(email)

            if len(items) < page_size:
                break
            page += 1
            if page > 10000:
                raise UserError(_("CleverReach-Paginierung wurde aus Sicherheitsgründen abgebrochen."))

        return result

    @staticmethod
    def _gl_event_chunks(items, size=1000):
        for pos in range(0, len(items), size):
            yield items[pos : pos + size]

    def _gl_event_mark_bulk_records(self, registrations, state, message):
        if not registrations:
            return
        registrations.with_context(gl_cr_skip_event_sync=True).sudo().write(
            {
                "gl_cr_newsletter_sync_state": state,
                "gl_cr_newsletter_synced_at": fields.Datetime.now(),
                "gl_cr_newsletter_sync_message": message,
                "gl_cr_newsletter_bulk_imported": True,
            }
        )

    def action_import_all_event_participants(self):
        """One-time import of historical attendees with full duplicate checks.

        Historical registrations predate the new checkbox. We intentionally do
        not fabricate a local opt-in flag/timestamp for those records.
        """
        self.ensure_one()

        if self.event_participant_bulk_imported_at:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Bestandsimport bereits abgeschlossen"),
                    "message": _("Der einmalige Teilnehmerimport wurde bereits am %s abgeschlossen.")
                    % self.event_participant_bulk_imported_at,
                    "type": "warning",
                    "sticky": True,
                },
            }

        group = self._gl_event_get_target_group(sync_if_missing=True)
        self._gl_event_ensure_name_attributes()
        Registration = self.env["event.registration"].sudo().with_context(active_test=False)
        registrations = Registration.search(
            [
                ("state", "in", ["open", "done"]),
                ("email", "!=", False),
            ],
            order="create_date desc, id desc",
        )

        # Local dedupe first; keep every registration record mapped to its e-mail
        # so all historical duplicates can receive the same sync status.
        email_to_regs = {}
        canonical = {}
        invalid_count = 0
        for registration in registrations:
            email = self._gl_event_normalize_email(registration.email)
            if not email:
                invalid_count += 1
                continue
            email_to_regs.setdefault(email, self.env["event.registration"].browse([]))
            email_to_regs[email] |= registration
            if email not in canonical:
                canonical[email] = registration

        local_duplicate_count = max(
            0,
            sum(len(recs) for recs in email_to_regs.values()) - len(canonical),
        )

        # Remote duplicate test is completed for the whole group BEFORE uploads.
        existing_emails = self._gl_event_fetch_existing_emails(group)
        already_there = sorted(set(canonical) & existing_emails)
        to_upload = sorted(set(canonical) - existing_emails)

        for email in already_there:
            self._gl_event_mark_bulk_records(
                email_to_regs[email],
                "exists",
                _("Beim Bestandsimport bereits in CleverReach vorhanden."),
            )

        payload_by_email = {}
        for email in to_upload:
            registration = canonical[email]
            payload_by_email[email] = self._gl_event_receiver_payload(
                registration,
                source="Odoo Event Teilnehmer - manueller Bestandsimport",
                activated_at=fields.Datetime.now(),
            )

        imported_emails = []
        failed = {}
        single_path = "/groups/%s/receivers" % group.external_id
        bulk_path = "/groups/%s/receivers/insert" % group.external_id

        # CleverReach provides a dedicated multi-receiver insert endpoint.
        for email_batch in self._gl_event_chunks(to_upload, 1000):
            payload_batch = [payload_by_email[email] for email in email_batch]
            try:
                self._api("POST", bulk_path, payload=payload_batch)
                imported_emails.extend(email_batch)
                continue
            except Exception as batch_exc:
                _logger.warning(
                    "CleverReach bulk receiver upload failed; retrying individually: %s",
                    batch_exc,
                )

            # A single invalid/blocked address must not discard a whole batch.
            for email in email_batch:
                try:
                    # Recheck in case the failed stack was partly accepted remotely.
                    if self._gl_event_receiver_exists(group, email):
                        imported_emails.append(email)
                        continue
                    self._api("POST", single_path, payload=payload_by_email[email])
                    imported_emails.append(email)
                except Exception as exc:
                    failed[email] = str(exc)

        for email in imported_emails:
            self._gl_event_mark_bulk_records(
                email_to_regs[email],
                "synced",
                _("Beim manuellen Bestandsimport zu CleverReach übertragen."),
            )

        for email, error in failed.items():
            email_to_regs[email].with_context(gl_cr_skip_event_sync=True).sudo().write(
                {
                    "gl_cr_newsletter_sync_state": "error",
                    "gl_cr_newsletter_sync_message": error[:1000],
                }
            )

        imported_count = len(set(imported_emails))
        existing_count = len(already_there)
        skipped_count = invalid_count + local_duplicate_count

        if failed:
            message = _(
                "%s neue Empfänger übertragen, %s bereits vorhanden, %s lokal "
                "übersprungen. %s Empfänger konnten noch nicht übertragen werden. "
                "Der Bestandsimport ist deshalb NICHT als abgeschlossen markiert; "
                "ein erneuter Klick ist durch die Duplikatprüfung sicher."
            ) % (imported_count, existing_count, skipped_count, len(failed))
            self.write(
                {
                    "event_participant_bulk_imported_count": imported_count,
                    "event_participant_bulk_existing_count": existing_count,
                    "event_participant_bulk_skipped_count": skipped_count,
                    "event_participant_bulk_last_message": message,
                }
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Bestandsimport teilweise ausgeführt"),
                    "message": message,
                    "type": "warning",
                    "sticky": True,
                },
            }

        message = _(
            "%s neue eindeutige Empfänger übertragen; %s waren bereits in "
            "CleverReach vorhanden; %s Datensätze wurden lokal wegen ungültiger "
            "oder doppelter E-Mail-Adresse übersprungen."
        ) % (imported_count, existing_count, skipped_count)
        self.write(
            {
                "event_participant_bulk_imported_at": fields.Datetime.now(),
                "event_participant_bulk_imported_count": imported_count,
                "event_participant_bulk_existing_count": existing_count,
                "event_participant_bulk_skipped_count": skipped_count,
                "event_participant_bulk_last_message": message,
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("CleverReach-Bestandsimport abgeschlossen"),
                "message": message,
                "type": "success",
                "sticky": True,
            },
        }
