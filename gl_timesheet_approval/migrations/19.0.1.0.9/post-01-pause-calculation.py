from odoo import SUPERUSER_ID, api, fields


def migrate(cr, version):
    """Convert snapshots created with the pre-1.0.9 pause formula.

    Old semantics for days > 6h:
        gross = actual worked time
        payable = gross - break

    New semantics:
        payable/working time = actual worked time
        gross = working time + break
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Day = env["gl.timesheet.day"].sudo()
    ReviewLog = env["gl.timesheet.review.log"].sudo()

    # Select only rows that still exactly match the former calculation. This makes
    # the migration idempotent and avoids touching any manually/newly corrected row.
    days = Day.search([("break_seconds", ">", 0)])
    affected_employee_lines = env["gl.timesheet.employee.month"].sudo().browse()

    for day in days:
        old_gross = int(day.gross_seconds or 0)
        old_break = int(day.break_seconds or 0)
        old_payable = int(day.payable_seconds or 0)
        if old_payable != max(0, old_gross - old_break):
            continue

        day.write(
            {
                "gross_seconds": old_gross + old_break,
                "payable_seconds": old_gross,
                "reviewer1_state": "pending",
                "reviewer1_by_id": False,
                "reviewer1_at": False,
                "reviewer2_state": "pending",
                "reviewer2_by_id": False,
                "reviewer2_at": False,
            }
        )
        employee_line = day.employee_month_id
        affected_employee_lines |= employee_line
        ReviewLog.create(
            {
                "month_id": day.month_id.id,
                "employee_month_id": employee_line.id,
                "day_id": day.id,
                "action": "calculation_changed",
                "note": (
                    "Berechnungslogik auf Version 19.0.1.0.9 korrigiert: "
                    "30 Minuten Pause werden bei mehr als 6 Stunden zur Bruttozeit "
                    "addiert und nicht von der Arbeitszeit abgezogen."
                ),
                "created_at": fields.Datetime.now(),
            }
        )

    if affected_employee_lines:
        affected_employee_lines.filtered("paid").write(
            {"paid": False, "paid_by_id": False, "paid_at": False}
        )
        # Recompute the stored summaries immediately so the portal and Excel export
        # are already correct when the module upgrade finishes.
        affected_employee_lines._compute_totals()
        affected_employee_lines._compute_approval_state()
        affected_employee_lines.mapped("month_id")._compute_summary()
        env.flush_all()
