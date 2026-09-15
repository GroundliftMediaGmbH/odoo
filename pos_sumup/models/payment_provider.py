# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import requests
from odoo import fields, models
from ..const import SUMUP_BASE_URL

_logger = logging.getLogger(__name__)

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'
    
    code = fields.Selection(selection_add=[('sumup', 'Sumup')], ondelete={'sumup': 'set default'})
    sumup_merchant_code = fields.Char(string='Merchant Code', required_if_provider='sumup')
    sumup_api_key = fields.Char(string='API Key', required_if_provider='sumup')

    def sumup_make_request(self, endpoint, data=None, method='POST', params=None):
        self.ensure_one()
        url = SUMUP_BASE_URL + endpoint
        
        headers = {
            'Authorization': f'Bearer {self.sumup_api_key}',
            'Content-Type': 'application/json',
        }

        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=60)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, json=data, timeout=60)
            else:
                response = requests.get(url, headers=headers, params=params, timeout=10)
            
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        except requests.exceptions.Timeout:
            _logger.error("SumUp API Timeout")
            return {'error': {'code': 'TIMEOUT', 'message': 'Connection timed out.'}}
        except requests.exceptions.ConnectionError:
            _logger.error("SumUp Connection Error")
            return {'error': {'code': 'NETWORK_ERROR', 'message': 'Could not connect to SumUp.'}}
        except requests.exceptions.HTTPError as e:
            _logger.error("SumUp API HTTP Error: %s", e)
            if response.status_code in (401, 403):
                 return {'error': {'code': 'AUTH_ERROR', 'message': 'Authentication failed. Check API Key.'}}
            
            # Try to get more details from the response body for 400/422
            try:
                error_data = response.json()
                error_msg = error_data.get('message') or error_data.get('error_description') or str(e)
                error_code = error_data.get('error_code', 'API_ERROR')
                return {'error': {'code': error_code, 'message': f"SumUp: {error_msg}"}}
            except ValueError:
                pass
                
            return {'error': {'code': 'API_ERROR', 'message': str(e)}}
        except requests.exceptions.RequestException as e:
            _logger.error("SumUp API Error: %s", e)
            return {'error': {'code': 'UNKNOWN_ERROR', 'message': str(e)}}
