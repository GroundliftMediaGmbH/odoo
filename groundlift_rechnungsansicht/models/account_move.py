# -*- coding: utf-8 -*-
import re

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _groundlift_invoice_display_number(self):
        """Return the customer-facing invoice number for the Groundlift PDF layout.

        Odoo's internal sequence can contain slashes, for example ``RE/2026/0003``.
        The Groundlift invoice layout must print this as ``RE202600003``:
        prefix + year/period + last sequence block padded to five digits.
        """
        self.ensure_one()
        raw_number = (self.name if self.name and self.name != "/" else False) or self.ref or "Entwurf"
        raw_number = str(raw_number).strip()

        parts = raw_number.split("/")
        if len(parts) >= 3 and parts[-1].isdigit():
            return "".join(parts[:-1]) + parts[-1].zfill(5)

        return re.sub(r"[^0-9A-Za-z]+", "", raw_number) or "Entwurf"
