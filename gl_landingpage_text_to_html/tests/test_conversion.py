"""Odoo-side regression coverage: run with Odoo's test infrastructure."""
from odoo.tests import TransactionCase
from ..models.conversion import plain_to_html, html_to_plain


class TestConversion(TransactionCase):
    def test_escaping_and_newlines(self):
        self.assertEqual(plain_to_html('A & B\n\nC < D'), 'A &amp; B<br/><br/>C &lt; D')

    def test_editor_to_plain(self):
        self.assertEqual(html_to_plain('<p>Hallo <strong>Welt</strong></p><p><a href="/event">Mehr</a></p>'), 'Hallo Welt\nMehr')
