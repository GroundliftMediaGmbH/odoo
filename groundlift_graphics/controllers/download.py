import base64
import io
import zipfile

from odoo import http
from odoo.http import request


class GroundliftGraphicsDownloadController(http.Controller):
    @http.route('/groundlift_graphics/poster/<int:poster_id>/outputs.zip', type='http', auth='user')
    def download_outputs_zip(self, poster_id, **kwargs):
        poster = request.env['gl.graphics.poster'].browse(poster_id)
        poster.check_access_rights('read')
        poster.check_access_rule('read')
        if not poster.exists() or not poster.output_ids:
            return request.not_found()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for output in poster.output_ids.sorted(key=lambda o: (o.template_name or '', o.id)):
                data = base64.b64decode(output.image or b'')
                zf.writestr(output.filename or f'{output.template_key}.jpg', data)
        buffer.seek(0)
        filename = f"{poster.name or 'grafiken'}_alle_ausgaben.zip".replace('/', '_')
        headers = [
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', http.content_disposition(filename)),
        ]
        return request.make_response(buffer.read(), headers=headers)
