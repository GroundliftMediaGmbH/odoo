import re

from odoo import api, fields, models


class GroundliftTodoPhase(models.Model):
    _name = "gl.todo.phase"
    _description = "Gemeinsame To-Do-Phase"
    _order = "sequence, id"

    name = fields.Char(string="Name", required=True)
    sequence = fields.Integer(string="Reihenfolge", default=10)
    active = fields.Boolean(string="Aktiv", default=True)
    fold = fields.Boolean(string="Eingeklappt", default=False)
    system_key = fields.Char(
        string="Systemschlüssel",
        copy=False,
        readonly=True,
        index=True,
        help="Technischer Schlüssel der Groundlift-Standardphasen.",
    )

    @api.model
    def _standard_phase_specs(self):
        return [
            ("inbox", "Eingang", 10, False),
            ("today", "Heute", 20, False),
            ("this_week", "Diese Woche", 30, False),
            ("this_month", "Diesen Monat", 40, False),
            ("later", "Später", 50, False),
            ("done", "Erledigt", 60, True),
            ("cancelled", "Abgebrochen", 70, True),
        ]

    @api.model
    def _ensure_standard_phases(self):
        """Legt Standardphasen idempotent nach dem Registry-Aufbau an.

        Bewusst nicht als Feld-Default: Bei einem neuen gespeicherten Feld kann
        Odoo Defaults bereits während der Schema-Initialisierung auswerten. Ein
        Zugriff auf ein gleichzeitig neu angelegtes Modell wäre dort zu früh.
        """
        Phase = self.sudo().with_context(active_test=False)
        result = {}
        for key, name, sequence, fold in self._standard_phase_specs():
            phase = Phase.search([("system_key", "=", key)], limit=1)
            if not phase:
                # Falls eine Phase aus einer früheren Version ohne system_key
                # existiert, übernehmen wir sie statt ein Duplikat zu erzeugen.
                candidates = Phase.search([("system_key", "=", False)])
                phase = candidates.filtered(
                    lambda p: self._system_key_from_name(p.name) == key
                )[:1]
            if not phase:
                phase = Phase.create({
                    "name": name,
                    "sequence": sequence,
                    "active": True,
                    "fold": fold,
                    "system_key": key,
                })
            else:
                vals = {}
                if not phase.system_key:
                    vals["system_key"] = key
                if not phase.active:
                    vals["active"] = True
                # Standardreihenfolge/Fold nur beim erstmaligen Übernehmen setzen;
                # spätere bewusste Benutzeränderungen bleiben erhalten.
                if vals:
                    phase.write(vals)
            result[key] = phase
        return result

    @api.model
    def _normalize_name(self, value):
        value = (value or "").strip().lower()
        value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        return re.sub(r"[^a-z0-9]+", " ", value).strip()

    @api.model
    def _system_key_from_name(self, name):
        normalized = self._normalize_name(name)
        aliases = {
            "inbox": "inbox",
            "eingang": "inbox",
            "today": "today",
            "heute": "today",
            "this week": "this_week",
            "diese woche": "this_week",
            "this month": "this_month",
            "diesen monat": "this_month",
            "dieser monat": "this_month",
            "later": "later",
            "spaeter": "later",
            "done": "done",
            "erledigt": "done",
            "cancelled": "cancelled",
            "canceled": "cancelled",
            "abgebrochen": "cancelled",
            "storniert": "cancelled",
        }
        return aliases.get(normalized)

    @api.model
    def _get_inbox_phase(self):
        return self._ensure_standard_phases()["inbox"]

    @api.model
    def _phase_from_personal_stage(self, stage):
        """Ordnet eine native persönliche Odoo-Phase unserer gemeinsamen Phase zu."""
        phases_by_key = self._ensure_standard_phases()
        if not stage:
            return phases_by_key["inbox"]

        Phase = self.sudo().with_context(active_test=False)
        system_key = self._system_key_from_name(stage.name)
        if system_key and system_key in phases_by_key:
            return phases_by_key[system_key]

        # Fallback für individuell umbenannte Standardphasen: Position innerhalb
        # der persönlichen Phasen des Mitarbeiters auf die gemeinsame Reihenfolge abbilden.
        if stage.user_id:
            user_stages = self.env["project.task.type"].sudo().search(
                [("user_id", "=", stage.user_id.id)], order="sequence, id"
            )
            if stage.id in user_stages.ids:
                index = user_stages.ids.index(stage.id)
                shared_phases = Phase.search([], order="sequence, id")
                if index < len(shared_phases):
                    return shared_phases[index]

        return phases_by_key["inbox"]

    def _matching_personal_stage(self, user):
        """Findet bzw. erzeugt für einen Benutzer die native persönliche Phase."""
        self.ensure_one()
        Stage = self.env["project.task.type"].sudo()
        user_stages = Stage.search([("user_id", "=", user.id)], order="sequence, id")

        if not user_stages:
            user_stages = Stage.with_context(
                lang=user.partner_id.lang,
                default_project_ids=False,
            ).create(
                self.env["project.task"].with_context(lang=user.partner_id.lang)
                ._get_default_personal_stage_create_vals(user.id)
            )

        if self.system_key:
            for stage in user_stages:
                if self._system_key_from_name(stage.name) == self.system_key:
                    return stage

        normalized_phase_name = self._normalize_name(self.name)
        for stage in user_stages:
            if self._normalize_name(stage.name) == normalized_phase_name:
                return stage

        shared_phases = self.sudo().with_context(active_test=False).search([], order="sequence, id")
        if self.id in shared_phases.ids:
            index = shared_phases.ids.index(self.id)
            if index < len(user_stages):
                return user_stages[index]

        return Stage.create({
            "name": self.name,
            "sequence": self.sequence,
            "user_id": user.id,
            "fold": self.fold,
        })
