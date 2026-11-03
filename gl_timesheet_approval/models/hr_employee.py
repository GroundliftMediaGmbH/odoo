# -*- coding: utf-8 -*-
import re
import unicodedata

from odoo import _, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Kept for upgrade compatibility with versions <= 19.0.1.0.3.
    # The import filter no longer uses this field; eligibility is determined
    # exclusively from Odoo structure_type_id.
    gl_timesheet_employment_type = fields.Selection(
        selection=[
            ("auto", "Automatisch aus Beschäftigungs-/Vertragsart"),
            ("minijob", "Minijob"),
            ("marginal", "Geringfügig beschäftigt"),
            ("exclude", "Nicht in der Stundenzettel-Prüfung anzeigen"),
        ],
        string="Frühere manuelle Beschäftigungsart",
        default="auto",
        required=True,
        help=(
            "Kompatibilitätsfeld aus einer früheren Modulversion. Für neue Einlesevorgänge "
            "wird ausschließlich das technische Odoo-Feld structure_type_id ausgewertet."
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
        string="Erkannter Strukturtyp",
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

    def _gl_timesheet_structure_type_records(self, on_date=None):
        """Return records in historical priority order for structure_type_id lookup."""
        self.ensure_one()
        records = []

        # Odoo 19 stores dated payroll/employment data on hr.version. The
        # version valid on the attendance date is authoritative for old months.
        if on_date and hasattr(self, "_get_version"):
            version = self.sudo()._get_version(on_date)
            if version:
                records.append(version.sudo())

        for field_name in ("current_version_id", "current_contract_id", "contract_id"):
            if field_name in self._fields and self[field_name]:
                record = self[field_name].sudo()
                if record not in records:
                    records.append(record)

        employee = self.sudo()
        if employee not in records:
            records.append(employee)
        return records

    def _gl_timesheet_eligibility_details(self, on_date=None):
        """Accept only the requested values from the technical field structure_type_id."""
        self.ensure_one()
        allowed_names = {
            "minijob",
            "geringfugige beschaftigung",
        }
        found_field = False

        for record in self._gl_timesheet_structure_type_records(on_date=on_date):
            if "structure_type_id" not in record._fields:
                continue

            found_field = True
            structure_type = record["structure_type_id"]

            # The first record carrying structure_type_id is the historically
            # relevant record. An empty or different value must not fall back to
            # tags, job titles, contract types or another current record.
            if not structure_type:
                return False, _(
                    "structure_type_id ist leer (%(model)s)",
                    model=record._description or record._name,
                )

            structure_name = str(
                structure_type["name"]
                if "name" in structure_type._fields and structure_type["name"]
                else structure_type.display_name
            )
            normalized_name = self._gl_normalize_text(structure_name)
            if normalized_name in allowed_names:
                return True, _(
                    "structure_type_id: %(value)s",
                    value=structure_name,
                )

            return False, _(
                "structure_type_id: %(value)s (nicht Minijob/Geringfügige Beschäftigung)",
                value=structure_name,
            )

        if found_field:
            return False, _("structure_type_id ist leer")
        return False, _(
            "Technisches Feld 'structure_type_id' wurde auf der Mitarbeiterversion nicht gefunden"
        )

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
