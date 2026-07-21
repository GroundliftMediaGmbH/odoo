# -*- coding: utf-8 -*-
import re
import unicodedata

from odoo import _, api, fields, models


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
    gl_timesheet_is_eligible = fields.Boolean(
        string="Für Stundenzettel berücksichtigt",
        compute="_compute_gl_timesheet_detection",
    )
    gl_timesheet_detection_info = fields.Char(
        string="Erkannte Beschäftigungsart",
        compute="_compute_gl_timesheet_detection",
    )

    @staticmethod
    def _gl_normalize_text(value):
        value = unicodedata.normalize("NFKD", str(value or ""))
        value = "".join(character for character in value if not unicodedata.combining(character))
        value = value.lower().replace("ß", "ss")
        return re.sub(r"[^a-z0-9]+", " ", value).strip()

    def _gl_timesheet_text_values(self, record, field_name):
        """Return display texts without depending on optional HR/payroll modules."""
        if not record or field_name not in record._fields:
            return []
        value = record[field_name]
        if not value:
            return []

        field = record._fields[field_name]
        if field.type == "selection":
            selection = dict(field._description_selection(self.env))
            return [str(selection.get(value, value) or "")]
        if field.type in ("many2one", "one2many", "many2many"):
            return [text for text in value.mapped("display_name") if text]
        return [str(value)]

    def _gl_timesheet_contract_like_records(self, on_date=None):
        self.ensure_one()
        records = []
        if on_date and hasattr(self, "_get_version"):
            version = self.sudo()._get_version(on_date)
            if version:
                records.append(version.sudo())
        for field_name in ("current_version_id", "current_contract_id", "contract_id"):
            if field_name in self._fields and self[field_name]:
                record = self[field_name].sudo()
                if record not in records:
                    records.append(record)
        return records

    def _gl_timesheet_candidate_field_names(self, record):
        """Find standard and Studio fields likely to contain employment classification."""
        preferred = [
            "contract_type_id",
            "employment_type_id",
            "employee_type_id",
            "employee_type",
            "employment_type",
            "contract_type",
            "category_ids",
            "job_id",
            "job_title",
            "name",
        ]
        result = [field_name for field_name in preferred if field_name in record._fields]

        field_tokens = (
            "employment",
            "employee type",
            "contract type",
            "beschaf",
            "beschaef",
            "anstell",
            "arbeitsverhaltnis",
            "arbeitsverhaeltnis",
            "beschaftigungsart",
            "beschaeftigungsart",
        )
        allowed_types = {"selection", "many2one", "many2many", "char", "text"}
        for field_name, field in record._fields.items():
            if field_name in result or field_name == "gl_timesheet_employment_type":
                continue
            if field.type not in allowed_types:
                continue
            descriptor = self._gl_normalize_text(f"{field_name} {field.string or ''}")
            if any(token in descriptor for token in field_tokens):
                result.append(field_name)
        return result

    def _gl_timesheet_eligibility_details(self, on_date=None):
        self.ensure_one()
        explicit = self.gl_timesheet_employment_type or "auto"
        if explicit == "minijob":
            return True, _("Manuell als Minijob markiert")
        if explicit == "marginal":
            return True, _("Manuell als geringfügig beschäftigt markiert")
        if explicit == "exclude":
            return False, _("Manuell ausgeschlossen")

        needles = (
            "minijob",
            "mini job",
            "geringfugig",
            "geringfuegig",
            "marginal employment",
            "marginally employed",
        )
        records = [self.sudo()] + self._gl_timesheet_contract_like_records(on_date=on_date)
        observed_values = []
        for record in records:
            for field_name in self._gl_timesheet_candidate_field_names(record):
                for text in self._gl_timesheet_text_values(record, field_name):
                    normalized = self._gl_normalize_text(text)
                    if not normalized:
                        continue
                    label = str(record._fields[field_name].string or field_name)
                    observed_values.append(f"{label}: {text}")
                    if any(needle in normalized for needle in needles):
                        return True, f"{label}: {text}"

        if observed_values:
            return False, _("Nicht als Minijob erkannt (%s)", "; ".join(observed_values[:3]))
        return False, _("Keine Beschäftigungs-/Vertragsart gefunden")

    def _gl_is_timesheet_eligible(self):
        self.ensure_one()
        eligible, _details = self._gl_timesheet_eligibility_details()
        return eligible

    def _compute_gl_timesheet_detection(self):
        for employee in self:
            eligible, details = employee._gl_timesheet_eligibility_details()
            employee.gl_timesheet_is_eligible = eligible
            employee.gl_timesheet_detection_info = details

    def _gl_get_timesheet_hourly_wage(self):
        self.ensure_one()
        if self.gl_timesheet_hourly_wage > 0:
            return self.gl_timesheet_hourly_wage

        for record in self._gl_timesheet_contract_like_records():
            # Prefer explicit hourly fields from payroll/localization/custom modules.
            for field_name in ("hourly_wage", "wage_hourly", "hourly_cost"):
                if field_name in record._fields and record[field_name]:
                    return float(record[field_name])

            wage = float(record["wage"] or 0.0) if "wage" in record._fields else 0.0
            if not wage:
                continue

            wage_type = ""
            for type_field in ("wage_type", "schedule_pay", "pay_type"):
                values = self._gl_timesheet_text_values(record, type_field)
                wage_type = self._gl_normalize_text(values[0]) if values else ""
                if wage_type:
                    break
            if any(token in wage_type for token in ("hour", "stund", "stuend")):
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
