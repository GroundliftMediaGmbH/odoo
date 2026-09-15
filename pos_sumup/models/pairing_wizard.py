import json

import requests
from odoo import fields, models, _
from odoo.exceptions import UserError

from ..const import SUMUP_BASE_URL

base_url = "https://api.sumup.com/v0.1"


class SumUpReaderPairingWizard(models.TransientModel):
    _name = 'sumup.reader.pairing.wizard'
    _description = 'SumUp Reader Pairing'

    pairing_code = fields.Char(
        string='Pairing Code',
        required=True,
        help='The pairing code displayed on the SumUp terminal.'
    )
    reader_name = fields.Char(
        string='Reader Name',
        required=True,
        default=lambda self: _('New SumUp Terminal'),
        help='A friendly name to identify the terminal in Odoo.'
    )

    def action_pair_reader(self):
        sumup_provider = self._get_sumup_payment_provider()

        endpoint = f"v0.1/merchants/{sumup_provider.sumup_merchant_code}/readers"
        url = SUMUP_BASE_URL + endpoint

        headers = {
            'Authorization': f'Bearer {sumup_provider.sumup_api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        payload = {
            "pairing_code": self.pairing_code,
            "name": self.reader_name,
            "meta": {}
        }
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if response.status_code != 201:
            raise UserError(response.json()['message'])

        data = response.json()
        self.env['sumup.terminal'].create({
            'name': data['name'],
            'terminal_id': data['id'],
        })

        return {'type': 'ir.actions.act_window_close'}

    def _get_sumup_payment_provider(self):
        sumup_payment_provider = self.env['payment.provider'].search([
            ('code', '=', 'sumup'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)

        if not sumup_payment_provider:
            raise UserError(_("Sumup payment provider for company %s is missing", self.env.company.name))

        return sumup_payment_provider
