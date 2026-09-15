# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

class SumUpTerminal(models.Model):
    _name = 'sumup.terminal'
    _description = 'SumUp Payment Terminal'

    name = fields.Char(string='Terminal Name', required=True)
    terminal_id = fields.Char(string='SumUp Reader ID', required=True)
