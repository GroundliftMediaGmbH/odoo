import base64

from odoo import http
from odoo.http import request


class GroundliftAiVideoMediaController(http.Controller):

    def _binary_response(self, payload, mimetype, filename=None):
        if not payload:
            return request.not_found()
        if isinstance(payload, str):
            payload = payload.encode()
        try:
            raw = base64.b64decode(payload)
        except Exception:
            return request.not_found()
        headers = [
            ('Content-Type', mimetype or 'application/octet-stream'),
            ('Content-Length', str(len(raw))),
            ('Cache-Control', 'public, max-age=3600'),
        ]
        if filename:
            headers.append(('Content-Disposition', f'inline; filename="{filename}"'))
        return request.make_response(raw, headers=headers)

    @http.route('/gl_ai_video/asset/<int:asset_id>/<string:token>', type='http', auth='public', methods=['GET'], csrf=False)
    def asset(self, asset_id, token, **kwargs):
        asset = request.env['gl.video.teaser.asset'].sudo().browse(asset_id).exists()
        if not asset or not asset.active or asset.public_token != token or asset.source_type != 'upload':
            return request.not_found()
        return self._binary_response(asset.file_data, asset.mime_type, asset.filename)

    @http.route('/gl_ai_video/scene/<int:scene_id>/<string:fmt>/<string:token>', type='http', auth='public', methods=['GET'], csrf=False)
    def scene(self, scene_id, fmt, token, **kwargs):
        scene = request.env['gl.video.teaser.scene'].sudo().browse(scene_id).exists()
        if not scene or scene.public_token != token or fmt not in ('16_9', '9_16'):
            return request.not_found()
        data = getattr(scene, f'runway_file_{fmt}')
        filename = getattr(scene, f'runway_filename_{fmt}')
        return self._binary_response(data, 'video/mp4', filename)

    @http.route('/gl_ai_video/job/<int:job_id>/<string:kind>/<string:token>', type='http', auth='public', methods=['GET'], csrf=False)
    def job_media(self, job_id, kind, token, **kwargs):
        job = request.env['gl.video.teaser.job'].sudo().browse(job_id).exists()
        if not job:
            return request.not_found()
        if kind in ('voice', 'music'):
            if job.media_token != token:
                return request.not_found()
            data = job.voice_file if kind == 'voice' else job.music_file
            filename = job.voice_filename if kind == 'voice' else job.music_filename
            return self._binary_response(data, 'audio/mpeg', filename)
        if kind in ('output_16_9', 'output_9_16'):
            if job.output_token != token:
                return request.not_found()
            data = job.output_16_9 if kind == 'output_16_9' else job.output_9_16
            filename = job.output_filename_16_9 if kind == 'output_16_9' else job.output_filename_9_16
            return self._binary_response(data, 'video/mp4', filename)
        return request.not_found()

    @http.route('/gl_ai_video/company_logo/<int:company_id>/<string:token>', type='http', auth='public', methods=['GET'], csrf=False)
    def company_logo(self, company_id, token, **kwargs):
        company = request.env['res.company'].sudo().browse(company_id).exists()
        if not company or company.gl_video_logo_token != token or not company.logo:
            return request.not_found()
        return self._binary_response(company.logo, 'image/png', 'logo.png')
