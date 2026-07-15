# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GlMediaApprovalVote(models.Model):
    _name = "gl.media.approval.vote"
    _description = "Medienfreigabe Stimme"
    _order = "voted_at desc"

    file_id = fields.Many2one("gl.media.approval.file", required=True, ondelete="cascade")
    folder_id = fields.Many2one(related="file_id.folder_id", store=True, readonly=True)
    person_id = fields.Many2one("gl.media.approval.person", required=True, ondelete="cascade")
    decision = fields.Selection([("approved", "Freigeben"), ("rejected", "Nicht freigeben")], required=True)
    voted_at = fields.Datetime(default=fields.Datetime.now, required=True)

    _sql_constraints = [
        ("uniq_vote_person_file", "unique(file_id, person_id)", "Pro Person ist nur eine Stimme je Datei erlaubt."),
    ]

    @api.constrains("person_id", "file_id")
    def _check_person_in_snapshot(self):
        for rec in self:
            if rec.person_id.id not in rec.file_id.approval_person_ids.ids:
                raise ValidationError(_("Die Person gehört nicht zum Freigabe-Kreis dieser Datei."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("file_id")._recompute_decision_state()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ("decision", "person_id", "file_id")):
            self.mapped("file_id")._recompute_decision_state()
        return res

    def unlink(self):
        files = self.mapped("file_id")
        res = super().unlink()
        files._recompute_decision_state()
        return res
