from odoo import api, models


TRUSTED_DEVICE_AGE_DAYS = 14
SECONDS_PER_DAY = 24 * 60 * 60


class AuthTotpDevice(models.Model):
    _inherit = 'auth_totp.device'

    @api.model
    def _get_trusted_device_age(self):
        """Return the lifetime of a trusted 2FA device in seconds.

        Odoo's auth_totp controller uses this value for both the server-side
        trusted-device expiration and the td_id cookie max-age.
        """
        return TRUSTED_DEVICE_AGE_DAYS * SECONDS_PER_DAY
