# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    @api.model
    def _groundlift_setup_invoice_report_actions(self):
        """Patch invoice report actions without relying on a single XML id.

        Odoo databases with Accounting localizations/Studio customizations may have
        more than one invoice report action. Searching by model/report_name keeps the
        module usable on Odoo.sh staging databases.
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
            "groundlift_rechnungsansicht.paperformat_groundlift_invoice_a4",
            raise_if_not_found=False,
        )
        if paperformat:
            vals["paperformat_id"] = paperformat.id

        if reports:
            reports.write(vals)
            _logger.info(
                "Groundlift Rechnungsansicht: patched %s invoice report action(s): %s",
                len(reports),
                ", ".join(reports.mapped("report_name")),
            )
        else:
            _logger.warning(
                "Groundlift Rechnungsansicht: no account.move QWeb PDF report action "
                "with report_name ilike 'report_invoice' found."
            )
        return True
