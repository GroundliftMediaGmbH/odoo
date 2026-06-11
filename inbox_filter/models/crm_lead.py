# -*- coding: utf-8 -*-
from odoo import models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def action_inbox_filter_sort(self):
        return self.env["inbox.filter.service"].run_sort_new_leads_action()

    def action_open_inbox_filter(self):
        return self.env.ref("inbox_filter.action_inbox_filter_workspace").read()[0]
