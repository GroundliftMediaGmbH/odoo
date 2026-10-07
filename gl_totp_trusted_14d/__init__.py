from . import models
from . import controllers


def post_init_hook(env):
    """Reset existing trusted-device grants once at installation.

    Odoo 19 normally creates trusted-device grants with its own default
    lifetime. Clearing existing grants guarantees that every browser/device
    starts using this module's 14-day lifetime after the next successful 2FA.
    Existing active web sessions are not logged out by this hook.
    """
    devices = env['auth_totp.device'].sudo().search([])
    if devices:
        devices._remove()
