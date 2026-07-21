# -*- coding: utf-8 -*-
import re
import unicodedata

from odoo import _, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Kept for upgrade compatibility with versions <= 19.0.1.0.3.
    # The import filter no longer uses this field; eligibility is determined
    # exclusively from the Odoo payment category.
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
            "wird ausschließlich die Odoo-Zahlungskategorie ausgewertet."
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
        string="Erkannte Zahlungskategorie",
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

    def _gl_timesheet_payment_category_records(self, on_date=None):
        """Return records in historical priority order for payment-category lookup."""
        self.ensure_one()
        records = []

        # Odoo 19 stores dated employee data in hr.version. The version valid on
        # the attendance date must take precedence over today's employee values.
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

    def _gl_timesheet_payment_category_field_names(self, record):
        """Find only fields whose technical name or caption denotes payment category."""
        preferred_names = {
            "payment_category",
            "payment_category_id",
            "payment_category_ids",
            "pay_category",
            "pay_category_id",
            "payroll_category",
            "payroll_category_id",
            "l10n_de_payment_category",
            "l10n_de_payment_category_id",
            "zahlungskategorie",
            "zahlungskategorie_id",
        }
        category_tokens = (
            "zahlungskategorie",
            "zahlung kategorie",
            "payment category",
            "pay category",
            "payroll category",
        )
        allowed_types = {"selection", "many2one", "many2many", "char", "text"}
        result = []

        for field_name, field in record._fields.items():
            if field.type not in allowed_types:
                continue
            normalized_name = self._gl_normalize_text(field_name)
            normalized_label = self._gl_normalize_text(field.string or "")
            descriptor = f"{normalized_name} {normalized_label}".strip()
            if field_name in preferred_names or any(token in descriptor for token in category_tokens):
                result.append(field_name)
        return result

    def _gl_timesheet_payment_category_values(self, record, field_name):
        """Return display labels and selection keys for exact category matching."""
        if not record or field_name not in record._fields:
            return []
        value = record[field_name]
        if not value:
            return []

        field = record._fields[field_name]
        if field.type == "selection":
            selection = dict(field._description_selection(self.env))
            values = [selection.get(value, value), value]
            return [str(item) for item in values if item not in (False, None, "")]
        if field.type in ("many2one", "one2many", "many2many"):
            return [text for text in value.mapped("display_name") if text]
        return [str(value)]

    def _gl_timesheet_eligibility_details(self, on_date=None):
        """Strictly accept the two requested values from the payment category."""
        self.ensure_one()
        allowed_labels = {
            "minijob",
            "mini job",
            "geringfugige beschaftigung",
            "geringfugig beschaftigt",
            # Same two Odoo categories when selection labels/keys are returned
            # in English or as technical selection values.
            "marginal employment",
            "marginally employed",
            "marginal employment germany",
            "marginal",
            "marginal employment type",
        }
        found_category_field = False
        found_empty_category = False

        for record in self._gl_timesheet_payment_category_records(on_date=on_date):
            for field_name in self._gl_timesheet_payment_category_field_names(record):
                found_category_field = True
                label = str(record._fields[field_name].string or field_name)
                values = self._gl_timesheet_payment_category_values(record, field_name)
                if not values:
                    found_empty_category = True
                    continue

                # A non-empty payment category on the historically most relevant
                # record is authoritative. Do not fall back to tags, job titles,
                # contract types or manual flags.
                display_value = values[0]
                normalized_values = {self._gl_normalize_text(value) for value in values}
                if normalized_values & allowed_labels:
                    return True, _("%(field)s: %(value)s", field=label, value=display_value)
                return False, _(
                    "%(field)s: %(value)s (nicht Minijob/Geringfügige Beschäftigung)",
                    field=label,
                    value=display_value,
                )

        if found_category_field or found_empty_category:
            return False, _("Zahlungskategorie ist leer")
        return False, _("Feld 'Zahlungskategorie' wurde nicht gefunden")

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
