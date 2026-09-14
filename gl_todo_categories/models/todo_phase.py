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

    _system_key_unique = models.Constraint(
        "UNIQUE(system_key)",
        "Der Systemschlüssel einer To-Do-Phase muss eindeutig sein.",
    )

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
        phase = self.sudo().with_context(active_test=False).search(
            [("system_key", "=", "inbox")], limit=1
        )
        if not phase:
            phase = self.sudo().create({
                "name": "Eingang",
                "sequence": 10,
                "active": True,
                "system_key": "inbox",
            })
        elif not phase.active:
            phase.sudo().write({"active": True})
        return phase

    @api.model
    def _phase_from_personal_stage(self, stage):
        """Ordnet eine native persönliche Odoo-Phase unserer gemeinsamen Phase zu."""
        if not stage:
            return self._get_inbox_phase()

        Phase = self.sudo().with_context(active_test=False)
        system_key = self._system_key_from_name(stage.name)
        if system_key:
            phase = Phase.search([("system_key", "=", system_key)], limit=1)
            if phase:
                return phase

        # Fallback für individuell umbenannte Standardphasen: Position innerhalb
        # der persönlichen Phasen des Mitarbeiters auf die gemeinsame Reihenfolge abbilden.
        user_stages = self.env["project.task.type"].sudo().search(
            [("user_id", "=", stage.user_id.id)], order="sequence, id"
        ) if stage.user_id else self.env["project.task.type"]
        if user_stages and stage in user_stages:
            index = list(user_stages.ids).index(stage.id)
            shared_phases = Phase.search([], order="sequence, id")
            if index < len(shared_phases):
                return shared_phases[index]

        # Letzter Fallback: erste Phase (Eingang).
        return self._get_inbox_phase()

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

        # Individuelle Phase: zuerst nach identischem Namen suchen.
        normalized_phase_name = self._normalize_name(self.name)
        for stage in user_stages:
            if self._normalize_name(stage.name) == normalized_phase_name:
                return stage

        # Danach positionsbasiert abbilden.
        shared_phases = self.sudo().with_context(active_test=False).search([], order="sequence, id")
        if self.id in shared_phases.ids:
            index = list(shared_phases.ids).index(self.id)
            if index < len(user_stages):
                return user_stages[index]

        # Für eine zusätzliche gemeinsame Phase erzeugen wir bei Bedarf auch eine
        # entsprechende persönliche Odoo-Phase, damit native Odoo-Funktionen konsistent bleiben.
        return Stage.create({
            "name": self.name,
            "sequence": self.sequence,
            "user_id": user.id,
            "fold": self.fold,
        })
