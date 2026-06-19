from markupsafe import Markup

from odoo import http
from odoo.http import request


class GroundliftGraphicsEditorPage(http.Controller):
    @http.route("/groundlift_graphics/editor/<int:poster_id>", type="http", auth="user")
    def graphics_editor_page(self, poster_id, **kwargs):
        poster = request.env["gl.graphics.poster"].browse(poster_id)
        poster.check_access_rights("read")
        poster.check_access_rule("read")
        if not poster.exists():
            return request.not_found()

        html = f"""<!doctype html>
<html lang="de">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Grafikeditor</title>
    <link rel="stylesheet" href="/web/static/lib/bootstrap/css/bootstrap.css"/>
    <link rel="stylesheet" href="/web/static/src/libs/fontawesome/css/font-awesome.css"/>
    <style>
        html, body {{ height: 100%; margin: 0; background: #151821; color: #f7f7f7; overflow: hidden; }}
        .gl-editor {{ height: 100vh; display: flex; flex-direction: column; }}
        .gl-toolbar {{ flex: 0 0 auto; height: 56px; display: flex; align-items: center; gap: 8px; padding: 8px 14px; background: #ffffff; color: #222; border-bottom: 1px solid #ddd; }}
        .gl-workspace {{ flex: 1 1 auto; min-height: 0; display: flex; }}
        .gl-sidebar {{ width: 390px; flex: 0 0 390px; overflow: auto; background: #fff; color: #222; border-right: 1px solid #ddd; padding: 16px; }}
        .gl-canvas-area {{ flex: 1 1 auto; min-width: 0; overflow: auto; display: flex; align-items: center; justify-content: center; padding: 24px; }}
        .gl-canvas-shell {{ background: #080a10; box-shadow: 0 16px 42px rgba(0,0,0,.55); }}
        #posterCanvas {{ display: block; max-width: min(100%, 1200px); max-height: calc(100vh - 120px); width: auto; height: auto; }}
        .gl-hidden {{ display: none !important; }}
        .gl-small {{ font-size: 12px; color: #666; }}
        .gl-section {{ border-bottom: 1px solid #eee; padding-bottom: 14px; margin-bottom: 14px; }}
        .gl-error {{ background: #3a1717; color: #ffd7d7; padding: 12px; white-space: pre-wrap; font-family: monospace; }}
    </style>
</head>
<body>
    <div id="gl-editor-root" data-poster-id="{poster_id}"></div>
    <script src="/groundlift_graphics/static/src/js/graphics_editor_standalone.js"></script>
</body>
</html>"""
        return request.make_response(Markup(html), headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route("/groundlift_graphics/editor/missing", type="http", auth="user")
    def graphics_editor_missing(self, **kwargs):
        return request.make_response(
            "<html><body style='font-family:sans-serif;padding:24px'>Keine Grafik-ID übergeben.</body></html>",
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )
