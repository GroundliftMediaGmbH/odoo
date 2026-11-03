import base64
from datetime import date, datetime

from odoo.tests.common import TransactionCase


class TestGraphicsPoster(TransactionCase):
    def test_split_event_name(self):
        poster_model = self.env["gl.graphics.poster"]
        title, subtitle = poster_model._split_event_name(
            "Mensch, Otto! - Zu Gast: Vanessa Eden"
        )
        self.assertEqual(title, "Mensch, Otto!")
        self.assertEqual(subtitle, "Zu Gast: Vanessa Eden")

    def test_filename_component_transliterates_umlauts(self):
        value = self.env["gl.graphics.poster"]._filename_component(
            "Kaulis Ü-40 Disco"
        )
        self.assertEqual(value, "Kaulis_ue_40_Disco")

    def test_output_filename_contains_dates_name_and_format(self):
        template = self.env["gl.graphics.template"].create(
            {"name": "Kino Test", "output_suffix": "Kino"}
        )
        event = self.env["event.event"].create(
            {
                "name": "Kaulis Ü-40 Disco - Tanz in den Mai",
                "date_begin": datetime(2026, 4, 30, 18, 0, 0),
                "date_end": datetime(2026, 4, 30, 21, 0, 0),
                "date_tz": "Europe/Berlin",
            }
        )
        filename = self.env["gl.graphics.poster"]._build_output_filename(
            event=event,
            template=template,
            base_name="Kaulis Ü-40 Disco",
            creation_date=date(2026, 6, 17),
        )
        self.assertEqual(
            filename,
            "20260617-20260430 Kaulis_ue_40_Disco_Kino.jpg",
        )


    def test_graphics_button_reuses_latest_active_poster(self):
        event = self.env["event.event"].create(
            {
                "name": "Grafik Wiederverwenden",
                "date_begin": datetime(2026, 9, 21, 17, 0, 0),
                "date_end": datetime(2026, 9, 21, 20, 0, 0),
                "date_tz": "Europe/Berlin",
            }
        )
        poster = self.env["gl.graphics.poster"].create({"event_id": event.id})
        action = event.action_create_graphics_poster()
        self.assertEqual(action["params"]["poster_id"], poster.id)
        self.assertEqual(
            self.env["gl.graphics.poster"].search_count([("event_id", "=", event.id)]),
            1,
        )

    def test_qr_generation_returns_png(self):
        value = self.env["gl.graphics.poster"].generate_qr_base64(
            "https://groundlift.de/event/test"
        )
        raw = base64.b64decode(value)
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
