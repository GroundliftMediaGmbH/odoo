from odoo import http
from odoo.http import request
from odoo.addons.auth_totp.controllers.home import Home as AuthTotpHome


class Home(AuthTotpHome):
    """Make the built-in Odoo trusted-device feature automatic.

    Odoo 19 only stores the trusted-device cookie if the user explicitly
    submits the TOTP form with the `remember` option. For Groundlift we force
    that option on every successful TOTP login. The actual lifetime is defined
    in models/auth_totp_device.py and is 14 days.
    """

    @http.route()
    def web_totp(self, redirect=None, **kwargs):
        if request.httprequest.method == 'POST' and kwargs.get('totp_token'):
            kwargs['remember'] = '1'
        return super().web_totp(redirect=redirect, **kwargs)
