# -*- coding: utf-8 -*-
from odoo import _, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    gl_timesheet_employment_type = fields.Selection(
        selection=[
            ("auto", "Automatisch aus Beschäftigungs-/Vertragsart"),
            ("minijob", "Minijob"),
            ("marginal", "Geringfügig beschäftigt"),
            ("exclude", "Nicht in der Stundenzettel-Prüfung anzeigen"),
        ],
        string="Stundenzettel-Beschäftigungsart",
        default="auto",
        required=True,
        help=(
            "Bei 'Automatisch' wird nach Begriffen wie Minijob oder geringfügig in der "
            "aktuellen Beschäftigungs-/Vertragsart gesucht. Die explizite Auswahl hat Vorrang."
        ),
    )
    gl_timesheet_hourly_wage = fields.Monetary(
        string="Stundenlohn für Stundenzettel",
        currency_field="gl_timesheet_currency_id",
        help=(
            "Optionaler Stundenlohn-Override. Wenn 0,00 eingetragen ist, versucht die App, "
            "einen als stündlich gekennzeichneten Lohn aus der aktuellen Beschäftigung zu lesen."
        ),
    )
    gl_timesheet_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
    )

    def _gl_timesheet_text_value(self, record, field_name):
        """Return a harmless display value without depending on optional HR modules."""
        if not record or field_name not in record._fields:
            return ""
        value = record[field_name]
        if not value:
            return ""
        if hasattr(value, "display_name"):
            return value.display_name or ""
        field = record._fields[field_name]
        if field.type == "selection":
            selection = field._description_selection(self.env)
            return dict(selection).get(value, value) or ""
        return str(value)

    def _gl_timesheet_contract_like_records(self):
        self.ensure_one()
        records = []
        for field_name in ("current_version_id", "current_contract_id", "contract_id"):
            if field_name in self._fields and self[field_name]:
                records.append(self[field_name].sudo())
        return records

    def _gl_is_timesheet_eligible(self):
        self.ensure_one()
        explicit = self.gl_timesheet_employment_type
        if explicit in ("minijob", "marginal"):
            return True
        if explicit == "exclude":
            return False

        needles = ("minijob", "mini-job", "geringfüg", "geringfueg")
        candidates = []
        for record in self._gl_timesheet_contract_like_records():
            for field_name in (
                "contract_type_id",
                "employment_type_id",
                "employee_type_id",
                "name",
            ):
                candidates.append(self._gl_timesheet_text_value(record, field_name))

        # Some databases keep the employment type directly on the employee.
        for field_name in ("contract_type_id", "employment_type_id"):
            candidates.append(self._gl_timesheet_text_value(self, field_name))

        normalized = " ".join(candidates).lower()
        return any(needle in normalized for needle in needles)

    def _gl_get_timesheet_hourly_wage(self):
        self.ensure_one()
        if self.gl_timesheet_hourly_wage > 0:
            return self.gl_timesheet_hourly_wage

        for record in self._gl_timesheet_contract_like_records():
            # Prefer an explicit hourly field when an installed localization provides one.
            for field_name in ("hourly_wage", "wage_hourly", "hourly_cost"):
                if field_name in record._fields and record[field_name]:
                    return float(record[field_name])

            wage = float(record["wage"] or 0.0) if "wage" in record._fields else 0.0
            if not wage:
                continue

            wage_type = ""
            for type_field in ("wage_type", "schedule_pay", "pay_type"):
                wage_type = self._gl_timesheet_text_value(record, type_field).lower()
                if wage_type:
                    break
            if any(token in wage_type for token in ("hour", "stünd", "stuend")):
                return wage

        return 0.0

    def action_open_gl_timesheet_months(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Stundenzettel-Monate"),
            "res_model": "gl.timesheet.employee.month",
            "view_mode": "list,form",
            "domain": [("employee_id", "=", self.id)],
            "context": {"default_employee_id": self.id},
        }
