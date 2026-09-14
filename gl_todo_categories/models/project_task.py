from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    gl_todo_category_id = fields.Many2one(
        "gl.todo.category",
        string="Kategorie",
        index=True,
        ondelete="set null",
        group_expand="_read_group_gl_todo_category_id",
        help="Gemeinsame Kategorie zur Organisation der To-Dos in der To-Do-App.",
    )
    gl_todo_phase_id = fields.Many2one(
        "gl.todo.phase",
        string="Phase",
        index=True,
        ondelete="restrict",
        default=lambda self: self.env["gl.todo.phase"]._get_inbox_phase(),
        group_expand="_read_group_gl_todo_phase_id",
        help=(
            "Gemeinsame To-Do-Phase. Anders als Odoos persönliche Phase ist sie "
            "auch für nicht zugewiesene To-Dos und in der Teamansicht eindeutig."
        ),
    )

    @api.model
    def _read_group_gl_todo_category_id(self, categories, domain):
        category_ids = categories.sudo()._search(
            [("active", "=", True)], order=categories._order
        )
        return categories.browse(category_ids)

    @api.model
    def _read_group_gl_todo_phase_id(self, phases, domain):
        phase_ids = phases.sudo()._search(
            [("active", "=", True)], order=phases._order
        )
        return phases.browse(phase_ids)

    @api.model
    def _gl_uncategorized_category(self):
        return self.env["gl.todo.category"]._get_uncategorized_category()

    @api.model
    def _gl_inbox_phase(self):
        return self.env["gl.todo.phase"]._get_inbox_phase()

    def _gl_sync_personal_stages_from_shared_phase(self):
        """Spiegelt die gemeinsame Board-Phase in Odoos persönliche Phasen."""
        Personal = self.env["project.task.stage.personal"].sudo()
        for task in self.filtered(
            lambda t: not t.project_id and not t.parent_id and t.gl_todo_phase_id and t.user_ids
        ):
            # Die user_ids-M2M und project.task.stage.personal verwenden dieselbe Tabelle.
            # Nach Zuweisungen stellen wir zunächst sicher, dass jede Relation eine Phase besitzt.
            task._populate_missing_personal_stages()
            personal_rows = Personal.search([("task_id", "=", task.id)])
            for personal in personal_rows:
                target_stage = task.gl_todo_phase_id._matching_personal_stage(personal.user_id)
                if target_stage and personal.stage_id != target_stage:
                    personal.with_context(gl_sync_from_shared_phase=True).write({
                        "stage_id": target_stage.id,
                    })

    @api.model_create_multi
    def create(self, vals_list):
        fallback_category = False
        inbox_phase = False
        default_project_id = self.env.context.get("default_project_id")
        default_parent_id = self.env.context.get("default_parent_id")

        for vals in vals_list:
            project_id = vals.get("project_id", default_project_id)
            parent_id = vals.get("parent_id", default_parent_id)
            is_private_top_level = not project_id and not parent_id

            if not is_private_top_level:
                continue

            # Ohne explizite Board-Phase beginnt ein To-Do im Eingang.
            if not vals.get("gl_todo_phase_id"):
                if not inbox_phase:
                    inbox_phase = self._gl_inbox_phase()
                vals["gl_todo_phase_id"] = inbox_phase.id

            # Nicht zugewiesene To-Dos gehören zwingend in "Unkategorisiert".
            # user_ids kann als ORM-Command-Liste kommen. Fehlt der Wert komplett,
            # überlassen wir die endgültige Prüfung dem Post-Create-Schritt.
            if "user_ids" in vals and not self._gl_vals_have_assignees(vals.get("user_ids")):
                if not fallback_category:
                    fallback_category = self._gl_uncategorized_category()
                vals["gl_todo_category_id"] = fallback_category.id
            elif not vals.get("gl_todo_category_id"):
                if not fallback_category:
                    fallback_category = self._gl_uncategorized_category()
                vals["gl_todo_category_id"] = fallback_category.id

        records = super().create(vals_list)
        private_todos = records.filtered(lambda t: not t.project_id and not t.parent_id)
        if private_todos:
            private_todos._gl_enforce_category_and_phase()
            private_todos._gl_sync_personal_stages_from_shared_phase()
        return records

    @api.model
    def _gl_vals_have_assignees(self, commands):
        """Best effort für M2M-Werte in create(). Die finale Wahrheit kommt aus record.user_ids."""
        if not commands:
            return False
        if isinstance(commands, (list, tuple)):
            # Direkte ID-Liste (z.B. aus action context)
            if commands and all(isinstance(item, int) for item in commands):
                return bool(commands)
            for command in commands:
                if not isinstance(command, (list, tuple)) or not command:
                    continue
                if command[0] == 6:
                    return bool(command[2])
                if command[0] == 4:
                    return True
                if command[0] == 5:
                    return False
        return True

    def _gl_enforce_category_and_phase(self):
        """Hält die beiden Groundlift-Regeln für private To-Dos invariant."""
        private_todos = self.filtered(lambda t: not t.project_id and not t.parent_id)
        if not private_todos:
            return

        fallback = self._gl_uncategorized_category()
        inbox = self._gl_inbox_phase()

        # Ohne Mitarbeiter MUSS die Kategorie "Unkategorisiert" sein.
        unassigned = private_todos.filtered(lambda t: not t.user_ids)
        if unassigned:
            super(ProjectTask, unassigned.with_context(gl_internal_fix=True)).write({
                "gl_todo_category_id": fallback.id,
            })

        # Auch zugewiesene To-Dos dürfen nicht kategorielos bleiben.
        missing_category = private_todos.filtered(lambda t: not t.gl_todo_category_id)
        if missing_category:
            super(ProjectTask, missing_category.with_context(gl_internal_fix=True)).write({
                "gl_todo_category_id": fallback.id,
            })

        # Die gemeinsame Phase ist immer gesetzt. Deshalb gibt es im Board keine
        # False-Gruppe/Spalte "Keine" mehr – auch bei unzugewiesenen To-Dos.
        missing_phase = private_todos.filtered(lambda t: not t.gl_todo_phase_id)
        if missing_phase:
            super(ProjectTask, missing_phase.with_context(gl_internal_fix=True)).write({
                "gl_todo_phase_id": inbox.id,
            })

    def write(self, vals):
        result = super().write(vals)

        if not self.env.context.get("gl_internal_fix"):
            private_todos = self.filtered(lambda t: not t.project_id and not t.parent_id)
            if private_todos:
                private_todos._gl_enforce_category_and_phase()

                if (
                    "gl_todo_phase_id" in vals
                    or "user_ids" in vals
                    or "project_id" in vals
                    or "parent_id" in vals
                ) and not self.env.context.get("gl_skip_personal_stage_sync"):
                    private_todos._gl_sync_personal_stages_from_shared_phase()

        return result

    @api.model
    def _gl_ensure_uncategorized_category_and_backfill(self):
        """Installations-/Upgrade-Migration für Kategorien und gemeinsame Phasen."""
        fallback = self._gl_uncategorized_category()
        inbox = self._gl_inbox_phase()
        Phase = self.env["gl.todo.phase"]
        Personal = self.env["project.task.stage.personal"].sudo()

        todos = self.sudo().with_context(active_test=False).search([
            ("project_id", "=", False),
            ("parent_id", "=", False),
        ])

        # 1) Alle unzugewiesenen To-Dos werden – wie gewünscht – unabhängig von
        # einer früheren Kategorie nach "Unkategorisiert" verschoben.
        unassigned = todos.filtered(lambda task: not task.user_ids)
        if unassigned:
            super(ProjectTask, unassigned.with_context(gl_internal_fix=True)).write({
                "gl_todo_category_id": fallback.id,
            })

        # 2) Sonstige kategorielose Altbestände ebenfalls auffüllen.
        without_category = todos.filtered(lambda task: not task.gl_todo_category_id)
        if without_category:
            super(ProjectTask, without_category.with_context(gl_internal_fix=True)).write({
                "gl_todo_category_id": fallback.id,
            })

        # 3) Gemeinsame Phase aus vorhandenen persönlichen Odoo-Phasen übernehmen.
        # Für nicht zugewiesene / phasenlose To-Dos ist "Eingang" der sichere Default.
        for task in todos.filtered(lambda task: not task.gl_todo_phase_id):
            personal = Personal.search([
                ("task_id", "=", task.id),
                ("stage_id", "!=", False),
            ], order="id", limit=1)
            phase = Phase._phase_from_personal_stage(personal.stage_id) if personal else inbox
            super(ProjectTask, task.with_context(gl_internal_fix=True)).write({
                "gl_todo_phase_id": phase.id,
            })

        # 4) Native persönliche Phasen der zugewiesenen To-Dos auf den gemeinsamen
        # Board-Stand synchronisieren. Unzugewiesene bleiben wirklich unzugewiesen.
        assigned = todos.filtered(lambda task: task.user_ids)
        if assigned:
            assigned._gl_sync_personal_stages_from_shared_phase()

        return True
