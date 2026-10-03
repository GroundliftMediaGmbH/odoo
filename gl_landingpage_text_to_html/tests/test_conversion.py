"""Odoo-side regression coverage: run with Odoo's test infrastructure."""
from odoo.tests import TransactionCase
from ..models.conversion import plain_to_html, html_to_plain
from ..models.event_event import _equivalent_text


class TestConversion(TransactionCase):
    def test_escaping_and_newlines(self):
        self.assertEqual(plain_to_html('A & B\n\nC < D'), 'A &amp; B<br/><br/>C &lt; D')

    def test_editor_to_plain(self):
        self.assertEqual(html_to_plain('<p>Hallo <strong>Welt</strong></p><p><a href="/event">Mehr</a></p>'), 'Hallo Welt\nMehr')

    def test_editor_paragraphs_and_bold_are_semantically_equal(self):
        self.assertTrue(_equivalent_text(
            '<p>Charmante Erzählkunst, die berührt</p>',
            '<p><strong>Charmante Erzählkunst, die berührt</strong></p>',
        ))
        self.assertFalse(_equivalent_text(
            '<p>Ein völlig anderer Website-Text</p>',
            '<p><strong>Charmante Erzählkunst, die berührt</strong></p>',
        ))
