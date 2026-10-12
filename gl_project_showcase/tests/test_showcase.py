import base64
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..models.media import safe_mime, vimeo_embed


class TestProjectShowcase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({'name': 'Showcase Testprojekt'})
        cls.showcase = cls.env['gl.project.showcase'].create({
            'name': 'Testshowcase', 'project_id': cls.project.id,
            'website_id': cls.env['website'].search([], limit=1).id,
        })

    def test_vimeo_links(self):
        self.assertEqual(vimeo_embed('https://vimeo.com/123456'), 'https://player.vimeo.com/video/123456')
        self.assertEqual(vimeo_embed('https://vimeo.com/showcase/12345'), 'https://vimeo.com/showcase/12345/embed')
        self.assertEqual(vimeo_embed('https://vimeo.com/123/abcdef1234'),
                         'https://player.vimeo.com/video/123?h=abcdef1234')
        self.assertFalse(vimeo_embed('https://evil.example/1234'))
        self.assertFalse(vimeo_embed('javascript:alert(1)'))
        self.assertFalse(vimeo_embed('https://vimeo.com.evil.example/123'))

    def test_unique_project(self):
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env['gl.project.showcase'].create({'project_id': self.project.id, 'name': 'Doppelt'})

    def test_password_before_publish(self):
        with self.assertRaises(ValidationError):
            self.showcase.write({'visibility': 'password', 'published': True})
        self.showcase._set_new_password('EinSicheresPasswort2026!')
        self.showcase.write({'visibility': 'password', 'published': True})
        self.assertTrue(self.showcase.published)
        self.assertNotEqual(self.showcase.password_hash, 'EinSicheresPasswort2026!')

    def test_preview_only_pdf_or_images(self):
        pdf = b'%PDF-1.7\n1 0 obj\nendobj\n%%EOF'
        self.assertEqual(safe_mime(pdf), 'application/pdf')
        doc = self.env['gl.showcase.document'].create({
            'name': 'Ergebnis-PDF', 'showcase_id': self.showcase.id,
            'filename': 'ergebnis.pdf', 'data': base64.b64encode(pdf), 'allow_download': False,
        })
        self.assertTrue(doc.has_preview)
        with self.assertRaises(ValidationError):
            self.env['gl.showcase.document'].create({
                'name': 'Office-Datei', 'showcase_id': self.showcase.id,
                'filename': 'bericht.docx', 'data': base64.b64encode(b'not-a-renderable-document'),
                'allow_download': False,
            })

    def test_invalid_color(self):
        with self.assertRaises(ValidationError):
            self.showcase.write({'color_accent': 'red; background:red'})
