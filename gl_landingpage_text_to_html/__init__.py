from . import models
from . import controllers


def post_init_hook(env):
    """Initial installation: backfill HTML and synchronize the website fallback."""
    env['event.event'].sudo()._gl_migrate_existing()
