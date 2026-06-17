import base64

from odoo.tests.common import TransactionCase


class TestGraphicsPoster(TransactionCase):
    def test_split_event_name(self):
        poster_model = self.env["gl.graphics.poster"]
        title, subtitle = poster_model._split_event_name(
            "Mensch, Otto! - Zu Gast: Vanessa Eden"
        )
        self.assertEqual(title, "Mensch, Otto!")
        self.assertEqual(subtitle, "Zu Gast: Vanessa Eden")

    def test_qr_generation_returns_png(self):
        value = self.env["gl.graphics.poster"].generate_qr_base64(
            "https://groundlift.de/event/test"
        )
        raw = base64.b64decode(value)
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
