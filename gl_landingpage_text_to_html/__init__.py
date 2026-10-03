from . import models
from . import controllers


def post_init_hook(env):
    env['event.event'].sudo()._gl_migrate_existing()
