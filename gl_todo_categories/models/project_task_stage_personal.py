from odoo import models


class ProjectTaskStagePersonal(models.Model):
    _inherit = "project.task.stage.personal"

    def write(self, vals):
        result = super().write(vals)

        # Wird die persönliche Odoo-Phase außerhalb unseres Boards geändert,
        # spiegeln wir sie zurück in die gemeinsame Board-Phase.
        if "stage_id" in vals and not self.env.context.get("gl_sync_from_shared_phase"):
            Phase = self.env["gl.todo.phase"]
            for personal in self:
                task = personal.task_id
                if (
                    task
                    and not task.project_id
                    and not task.parent_id
                    and personal.stage_id
                ):
                    phase = Phase._phase_from_personal_stage(personal.stage_id)
                    if phase and task.gl_todo_phase_id != phase:
                        task.with_context(
                            gl_skip_personal_stage_sync=True
                        ).write({"gl_todo_phase_id": phase.id})

        return result
