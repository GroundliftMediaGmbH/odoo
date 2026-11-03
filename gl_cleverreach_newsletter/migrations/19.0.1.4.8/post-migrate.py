# -*- coding: utf-8 -*-
"""Keep the previously available spontaneous automation switched on at upgrade.

A new stored Boolean can otherwise be false on old config rows even though its
Python default is True. This migration runs only on module upgrade, not when a
user subsequently disables spontaneous newsletters on the new version.
"""


def migrate(cr, version):
    if version:
        cr.execute("""
            UPDATE gl_cleverreach_newsletter_config
               SET spontaneous_enabled = TRUE
        """)
