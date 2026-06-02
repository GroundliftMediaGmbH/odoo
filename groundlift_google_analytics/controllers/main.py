# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class GroundliftGoogleAnalyticsDashboard(http.Controller):
    """Internal Odoo page for the embedded Google Analytics / Looker Studio dashboard."""

    @http.route(
        "/groundlift/google-analytics",
        type="http",
        auth="user",
        website=False,
        sitemap=False,
    )
    def google_analytics_dashboard(self, **kwargs):
        html = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Google Analytics Dashboard</title>
    <style>
        :root {
            color-scheme: dark;
            --bg: #111318;
            --panel: #181b22;
            --border: rgba(255, 255, 255, 0.12);
            --text: #f4f4f5;
            --muted: #a1a1aa;
            --accent: #7c3aed;
        }

        * {
            box-sizing: border-box;
        }

        html,
        body {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: var(--bg);
            color: var(--text);
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
        }

        .gl-header {
            height: 56px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 0 18px;
            background: linear-gradient(135deg, #171922 0%, #111318 100%);
            border-bottom: 1px solid var(--border);
        }

        .gl-title {
            display: flex;
            align-items: baseline;
            gap: 10px;
            min-width: 0;
        }

        .gl-title strong {
            font-size: 16px;
            font-weight: 700;
            letter-spacing: 0.01em;
            white-space: nowrap;
        }

        .gl-title span {
            color: var(--muted);
            font-size: 13px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .gl-actions {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-shrink: 0;
        }

        .gl-button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 34px;
            padding: 0 13px;
            border: 1px solid var(--border);
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.06);
            color: var(--text);
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
        }

        .gl-button:hover {
            background: rgba(255, 255, 255, 0.10);
            border-color: rgba(255, 255, 255, 0.20);
            transform: translateY(-1px);
        }

        .gl-frame-wrap {
            width: 100%;
            height: calc(100vh - 56px);
            background: #0b0c10;
        }

        iframe {
            display: block;
            width: 100%;
            height: 100%;
            border: 0;
            background: #ffffff;
        }

        @media (max-width: 720px) {
            .gl-title span {
                display: none;
            }

            .gl-header {
                padding: 0 12px;
            }
        }
    </style>
</head>
<body>
    <header class="gl-header">
        <div class="gl-title">
            <strong>Google Analytics</strong>
            <span>Looker Studio Dashboard</span>
        </div>
        <div class="gl-actions">
            <a class="gl-button" href="/odoo">Zurück zu Odoo</a>
            <a class="gl-button" href="https://datastudio.google.com/embed/reporting/d0b52726-5b18-4edc-a618-89fc46ec6b1c/page/Tp2zF" target="_blank" rel="noopener noreferrer">Extern öffnen</a>
        </div>
    </header>

    <main class="gl-frame-wrap">
        <iframe
            width="600"
            height="443"
            src="https://datastudio.google.com/embed/reporting/d0b52726-5b18-4edc-a618-89fc46ec6b1c/page/Tp2zF"
            frameborder="0"
            style="border:0"
            allowfullscreen
            sandbox="allow-storage-access-by-user-activation allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox">
        </iframe>
    </main>
</body>
</html>"""
        return request.make_response(
            html,
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )
