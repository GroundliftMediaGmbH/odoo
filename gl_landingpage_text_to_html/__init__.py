from . import models
from . import controllers


def post_init_hook(env):
    """Initial installation: backfill HTML and safely bind the native page."""
    env['event.event'].sudo()._gl_migrate_existing()
