# -*- coding: utf-8 -*-
"""Initialize the *new* 4.8 switch on upgrades from pre-4.8 releases only.

Existing 4.8+ values, including False, are NEVER rewritten. This migration
runs only when upgrading the module, not on ordinary saves or form reloads.
"""
import re


def migrate(cr, version):
    if not version:
        return
    nums = tuple(int(x) for x in re.findall(r"\d+", version)[:5])
    nums += (0,) * (5 - len(nums))
    if nums < (19, 0, 1, 4, 8):
        cr.execute("""
            UPDATE gl_cleverreach_newsletter_config
               SET spontaneous_enabled = TRUE
        """)
