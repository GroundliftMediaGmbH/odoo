# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    @api.model
    def _groundlift_setup_invoice_report_actions(self):
        """Patch invoice report actions without depending on one brittle XML id.

        Odoo invoice report external IDs can differ slightly between editions/localizations.
        Searching by model + QWeb report name is safer on Odoo.sh databases that have
        been customized via Studio.
        """
        reports = self.sudo().search([
            ("model", "=", "account.move"),
            ("report_type", "=", "qweb-pdf"),
            ("report_name", "ilike", "report_invoice"),
        ])

        print_name_expr = (
            "(object.move_type == 'out_refund' and 'Gutschrift_%s' "
            "or object.move_type == 'out_invoice' and 'Rechnung_%s' "
            "or 'Beleg_%s') % "
            "((object.name or object.ref or 'Entwurf').replace('/', '_'))"
        )
        attachment_expr = (
            "(object.state == 'posted') and "
            "(((object.move_type == 'out_refund' and 'Gutschrift_%s' "
            "or object.move_type == 'out_invoice' and 'Rechnung_%s' "
            "or 'Beleg_%s') % "
            "((object.name or object.ref or 'Entwurf').replace('/', '_'))) + '.pdf')"
        )

        vals = {
            "name": "Rechnung",
            "print_report_name": print_name_expr,
            "attachment": attachment_expr,
        }

        paperformat = self.env.ref(
            "groundlift_invoice_layout.paperformat_groundlift_invoice_a4",
            raise_if_not_found=False,
        )
        if paperformat:
            vals["paperformat_id"] = paperformat.id

        if reports:
            reports.write(vals)
            _logger.info(
                "GROUNDLIFT invoice layout: patched %s invoice report action(s): %s",
                len(reports),
                ", ".join(reports.mapped("report_name")),
            )
        else:
            _logger.warning(
                "GROUNDLIFT invoice layout: no account.move QWeb PDF report action "
                "with report_name ilike 'report_invoice' found. Filename was not patched."
            )
        return True
