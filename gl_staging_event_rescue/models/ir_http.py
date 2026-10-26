"""Emergency redirect for links from the 2026-10-26 staging newsletter.

The guard is intentionally strict: it only applies to the named Odoo.sh staging
host while Odoo.sh reports ODOO_STAGE=staging. Production is never redirected.
"""

import os

from werkzeug.exceptions import abort
from werkzeug.utils import redirect

from odoo import models
from odoo.http import request


STAGING_HOST = "groundlift-main-staging-40401979.dev.odoo.com"
TARGET_URL = "https://groundlift.de/public-events.php"


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _match(cls, path):
        """Run before normal Odoo route matching, including paths that return 404."""
        http_request = request.httprequest
        host = http_request.host.split(":", 1)[0].lower()

        if (
            os.environ.get("ODOO_STAGE") == "staging"
            and host == STAGING_HOST
            and (path == "/event" or path.startswith("/event/"))
        ):
            response = redirect(TARGET_URL, code=302)
            response.headers["Cache-Control"] = "no-store, max-age=0"
            abort(response)

        return super()._match(path)
