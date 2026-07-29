import json
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

        html = """<!doctype html>
<html lang="de">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Grafikeditor</title>
    <link rel="stylesheet" href="/web/static/lib/bootstrap/css/bootstrap.css"/>
    <link rel="stylesheet" href="/web/static/src/libs/fontawesome/css/font-awesome.css"/>
    <style>
        :root {
            --gl-bg: #151821;
            --gl-panel: #ffffff;
            --gl-border: #d8dadd;
            --gl-text: #1f2328;
            --gl-muted: #6b7280;
            --gl-primary: #714b67;
            --gl-primary-hover: #5f3f57;
            --gl-secondary: #f4f5f7;
        }
        html, body { height: 100%; margin: 0; background: var(--gl-bg); color: #f7f7f7; overflow: hidden; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }
        .gl-editor { height: 100vh; display: flex; flex-direction: column; }
        .gl-toolbar { flex: 0 0 auto; min-height: 58px; display: flex; align-items: center; gap: 10px; padding: 10px 16px; background: #fff; color: var(--gl-text); border-bottom: 1px solid var(--gl-border); box-shadow: 0 1px 2px rgba(0,0,0,.06); }
        .gl-toolbar strong { font-size: 15px; font-weight: 600; max-width: 580px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .gl-workspace { flex: 1 1 auto; min-height: 0; display: flex; background: var(--gl-bg); }
        .gl-sidebar { width: 480px; flex: 0 0 480px; overflow: auto; background: var(--gl-panel); color: var(--gl-text); border-right: 1px solid var(--gl-border); padding: 18px; }
        .gl-canvas-area { flex: 1 1 auto; min-width: 0; overflow: auto; display: flex; align-items: center; justify-content: center; padding: 28px; background: radial-gradient(circle at 50% 30%, #252a36 0%, #151821 55%, #10131a 100%); }
        .gl-canvas-shell { background: #080a10; box-shadow: 0 18px 48px rgba(0,0,0,.55); border-radius: 6px; overflow: hidden; }
        #posterCanvas { display: block; max-width: min(100%, 1200px); max-height: calc(100vh - 126px); width: auto; height: auto; }
        .gl-section { border-bottom: 1px solid #eceef2; padding-bottom: 16px; margin-bottom: 16px; }
        .gl-label { display: block; margin: 0 0 5px 0; font-size: 13px; font-weight: 500; color: #343a40; }
        .gl-label-strong { font-size: 13px; font-weight: 700; color: #20242a; }
        .gl-input { width: 100%; min-height: 34px; border: 1px solid #cfd4dc; border-radius: 4px; padding: 6px 8px; font-size: 14px; color: var(--gl-text); background: #fff; box-sizing: border-box; }
        textarea.gl-input { resize: vertical; line-height: 1.3; }
        .gl-input:focus, .gl-color:focus { outline: none; border-color: var(--gl-primary); box-shadow: 0 0 0 2px rgba(113,75,103,.16); }
        .gl-color { width: 100%; height: 36px; border: 1px solid #cfd4dc; border-radius: 4px; background: #fff; padding: 2px; }
        .gl-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .gl-col { min-width: 0; }
        .gl-btn { appearance: none; border: 1px solid transparent; border-radius: 4px; padding: 6px 10px; font-size: 13px; line-height: 1.25; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 5px; text-decoration: none; white-space: nowrap; }
        .gl-btn-primary { background: var(--gl-primary); color: #fff; border-color: var(--gl-primary); }
        .gl-btn-primary:hover { background: var(--gl-primary-hover); border-color: var(--gl-primary-hover); }
        .gl-btn-secondary { background: #fff; color: var(--gl-primary); border-color: var(--gl-primary); }
        .gl-btn-secondary:hover { background: #f8f5f7; }
        .gl-btn-light { background: var(--gl-secondary); color: var(--gl-text); border-color: #d9dde3; }
        .gl-btn-light:hover { background: #e9ecef; }
        .w-100 { width: 100%; }
        .mb-2 { margin-bottom: 8px; }
        .d-flex { display: flex; }
        .gap-2 { gap: 8px; }
        .flex-fill { flex: 1 1 auto; }
        .flex-grow-1 { flex-grow: 1; }
        .gl-hidden { display: none !important; }
        .gl-small { font-size: 12px; color: var(--gl-muted); line-height: 1.35; }
        .gl-error { background: #3a1717; color: #ffd7d7; border-radius: 4px; padding: 12px; white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    </style>
</head>
<body>
    <div id="gl-editor-root" data-poster-id="__POSTER_ID__"></div>
    <script src="/groundlift_graphics/static/src/js/graphics_editor_standalone.js?v=19.0.1.6.0"></script>
</body>
</html>"""
        html = html.replace("__POSTER_ID__", str(poster_id))
        return request.make_response(Markup(html), headers=[("Content-Type", "text/html; charset=utf-8")])



    @http.route("/groundlift_graphics/template_defaults/<string:template_key>/save", type="http", auth="user", methods=["POST"], csrf=False)
    def save_template_defaults(self, template_key, **kwargs):
        payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        defaults = payload.get("defaults") or {}
        key = f"groundlift_graphics.template_defaults.{template_key}"
        request.env["ir.config_parameter"].sudo().set_param(key, json.dumps(defaults))
        return request.make_json_response({"ok": True})

    @http.route("/groundlift_graphics/template_defaults/<string:template_key>/load", type="http", auth="user", methods=["POST"], csrf=False)
    def load_template_defaults(self, template_key, **kwargs):
        key = f"groundlift_graphics.template_defaults.{template_key}"
        raw = request.env["ir.config_parameter"].sudo().get_param(key)
        if not raw:
            return request.make_json_response({"found": False, "defaults": None})
        try:
            return request.make_json_response({"found": True, "defaults": json.loads(raw)})
        except Exception:
            return request.make_json_response({"found": False, "defaults": None, "error": "Ungültige gespeicherte Standarddaten."})

    @http.route("/groundlift_graphics/editor/missing", type="http", auth="user")
    def graphics_editor_missing(self, **kwargs):
        return request.make_response(
            "<html><body style='font-family:sans-serif;padding:24px'>Keine Grafik-ID übergeben.</body></html>",
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )
