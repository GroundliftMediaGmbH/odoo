import base64
from odoo.exceptions import AccessError, ValidationError
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


    def test_missing_optional_pdf_library_does_not_crash_module(self):
        """A missing renderer cannot break registry loading or leak original PDFs."""
        from unittest.mock import patch
        from ..models import pdf_preview
        with patch.object(pdf_preview.importlib, 'import_module',
                          side_effect=ModuleNotFoundError('pypdfium2 not installed')):
            with self.assertRaises(pdf_preview.PdfPreviewError):
                pdf_preview.count_pdf_pages(b'%PDF-1.7\n%%EOF')

    def test_server_raster_pdf_preview(self):
        """A valid PDF is converted to images without shipping raw PDF bytes."""
        from io import BytesIO
        from PIL import Image
        from reportlab.pdfgen import canvas
        from ..models.pdf_preview import (
            PdfPreviewError, _load_pdfium, count_pdf_pages, render_pdf_page,
        )
        try:
            _load_pdfium()
        except PdfPreviewError:
            self.skipTest('pypdfium2 is not installed; install the Git-root requirements.txt to enable PDF previews')

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=(595, 842))
        pdf.drawString(80, 730, 'Showcase protected PDF page 1')
        pdf.showPage()
        pdf.drawString(80, 730, 'Showcase protected PDF page 2')
        pdf.showPage()
        pdf.save()
        source = buffer.getvalue()
        self.assertTrue(source.startswith(b'%PDF-'))
        self.assertEqual(count_pdf_pages(source), 2)
        image = render_pdf_page(source, 2)
        self.assertTrue(image.startswith(b'\xff\xd8\xff'))
        self.assertFalse(image.startswith(b'%PDF-'))
        with Image.open(BytesIO(image)) as jpg:
            self.assertEqual(jpg.format, 'JPEG')
        with self.assertRaises(PdfPreviewError):
            render_pdf_page(source, 3)

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

    def test_password_wizard_explicit_external_publication(self):
        """Setting a password can publish via the explicit wizard checkbox."""
        self.assertFalse(self.showcase.published)
        self.assertEqual(self.showcase.visibility, 'private')
        wizard = self.env['gl.showcase.password.wizard'].create({
            'showcase_id': self.showcase.id,
            'new_password': 'EinSicheresPasswort2026!',
            'confirm_password': 'EinSicheresPasswort2026!',
            'publish_now': True,
        })
        wizard.action_save()
        self.assertTrue(self.showcase.password_is_set)
        self.assertEqual(self.showcase.visibility, 'password')
        self.assertTrue(self.showcase.published)
        self.assertNotEqual(self.showcase.password_hash, 'EinSicheresPasswort2026!')

    def test_password_wizard_can_leave_draft_private(self):
        """The non-publication option must preserve drafts and privacy."""
        wizard = self.env['gl.showcase.password.wizard'].create({
            'showcase_id': self.showcase.id,
            'new_password': 'EinSicheresPasswort2026!',
            'confirm_password': 'EinSicheresPasswort2026!',
            'publish_now': False,
        })
        wizard.action_save()
        self.assertTrue(self.showcase.password_is_set)
        self.assertEqual(self.showcase.visibility, 'private')
        self.assertFalse(self.showcase.published)
        self.showcase.action_enable_password_access()
        self.assertTrue(self.showcase.published)
        self.assertEqual(self.showcase.visibility, 'password')

    def test_cannot_activate_password_access_without_password(self):
        with self.assertRaises(ValidationError):
            self.showcase.action_enable_password_access()
        self.assertFalse(self.showcase.published)

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

    def test_pdf_upload_binary_size_context(self):
        """Odoo 19 form reads may request size-only values of binary fields."""
        from ..models.media import decode_record_file
        pdf = b'%PDF-1.7\n1 0 obj\nendobj\n%%EOF'
        doc = self.env['gl.showcase.document'].create({
            'name': 'Upload aus Dialog',
            'showcase_id': self.showcase.id,
            'filename': 'upload.pdf',
            'data': base64.b64encode(pdf),
            'allow_download': False,
        })
        # The form may request human-readable bin_size while constraints
        # must always retrieve the full PDF instead of parsing that size.
        in_dialog = doc.with_context(bin_size=True, bin_size_data=True)
        self.assertEqual(decode_record_file(in_dialog, 'data'), pdf)
        in_dialog._validate_data()
        in_dialog._compute_mime_type()
        self.assertEqual(in_dialog.mime_type, 'application/pdf')
        self.assertTrue(in_dialog.has_preview)

    def test_base64_line_breaks_in_uploaded_data(self):
        from ..models.media import decode_file
        pdf = b'%PDF-1.7\n1 0 obj\nendobj\n%%EOF'
        encoded = base64.b64encode(pdf)
        self.assertEqual(decode_file(encoded[:12] + b'\r\n' + encoded[12:]), pdf)

    def test_invalid_color(self):
        with self.assertRaises(ValidationError):
            self.showcase.write({'color_accent': 'red; background:red'})

    def test_all_internal_users_see_and_manage_showcase(self):
        """No special editor group and no project write ACL required."""
        internal_group = self.env.ref('base.group_user')
        employee = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Showcase Mitarbeiter',
            'login': 'showcase-employee-test@example.invalid',
            'groups_id': [(6, 0, [internal_group.id])],
        })
        self.assertTrue(employee.has_group('base.group_user'))
        self.assertFalse(employee.has_group('project.group_project_manager'))
        self.project.write({'privacy_visibility': 'employees'})
        existing = self.env['gl.project.showcase'].with_user(employee).search([
            ('project_id', '=', self.project.id)
        ])
        self.assertEqual(existing, self.showcase)
        action = self.project.with_user(employee).action_gl_open_showcase()
        self.assertEqual(action['res_id'], self.showcase.id)

        project_new = self.env['project.project'].create({
            'name': 'Showcase neu anlegen ohne Projektleitung',
            'privacy_visibility': 'employees',
        })
        create_action = project_new.with_user(employee).action_gl_open_showcase()
        newly_created = self.env['gl.project.showcase'].browse(create_action['res_id'])
        self.assertEqual(newly_created.project_id.id, project_new.id)
        newly_created.with_user(employee).write({'subtitle': 'Bearbeitet durch Mitarbeiter'})
        self.assertEqual(newly_created.subtitle, 'Bearbeitet durch Mitarbeiter')

    def test_portal_has_no_showcase_backend_access(self):
        portal_group = self.env.ref('base.group_portal')
        portal_user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Showcase Portal Test',
            'login': 'showcase-portal-test@example.invalid',
            'groups_id': [(6, 0, [portal_group.id])],
        })
        self.assertFalse(portal_user.has_group('base.group_user'))
        with self.assertRaises(AccessError):
            self.env['gl.project.showcase'].with_user(portal_user).search([])

    def test_documents_attach_to_video_and_remain_in_same_showcase(self):
        """Attached files can be assigned from the Documents tab or video form."""
        video = self.env['gl.showcase.video'].create({
            'showcase_id': self.showcase.id, 'name': 'Kundenfilm',
            'vimeo_url': 'https://vimeo.com/123456',
        })
        file_bytes = b'%PDF-1.7\n1 0 obj\nendobj\n%%EOF'
        document = self.env['gl.showcase.document'].create({
            'name': 'Schnittliste', 'showcase_id': self.showcase.id,
            'filename': 'schnittliste.pdf', 'data': base64.b64encode(file_bytes),
            'video_id': video.id, 'allow_download': False,
        })
        self.assertEqual(video.document_ids, document)
        self.assertEqual(video.document_count, 1)
        self.assertTrue(document.has_preview)

        document.write({'video_id': False})
        self.assertFalse(video.document_ids)
        self.assertEqual(video.document_count, 0)
        self.assertIn(document, self.showcase.document_ids)

        second_project = self.env['project.project'].create({'name': 'Fremdes Showcase-Projekt'})
        second_showcase = self.env['gl.project.showcase'].create({
            'name': 'Fremdes Showcase', 'project_id': second_project.id,
        })
        foreign_video = self.env['gl.showcase.video'].create({
            'showcase_id': second_showcase.id, 'name': 'Anderes Video',
            'vimeo_url': 'https://vimeo.com/987654',
        })
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                document.write({'video_id': foreign_video.id})
        self.assertFalse(document.video_id)

    def test_gallery_tags_group_photos_and_enforce_showcase(self):
        """One photo can appear under several custom section headings."""
        from io import BytesIO
        from PIL import Image
        from odoo import fields

        buffer = BytesIO()
        Image.new('RGB', (8, 8), (120, 80, 40)).save(buffer, format='PNG')
        data = base64.b64encode(buffer.getvalue())

        photo_tag = self.env['gl.showcase.photo.tag']
        tag_one = photo_tag.create({
            'name': 'Aufbau', 'sequence': 5, 'showcase_id': self.showcase.id,
        })
        tag_two = photo_tag.create({
            'name': 'Show', 'sequence': 10, 'showcase_id': self.showcase.id,
        })
        photo = self.env['gl.showcase.photo'].create({
            'showcase_id': self.showcase.id, 'name': 'Bühne', 'photo': data,
            'tag_ids': [fields.Command.set([tag_one.id, tag_two.id])],
        })
        extra = self.env['gl.showcase.photo'].create({
            'showcase_id': self.showcase.id, 'name': 'Ohne Tag', 'photo': data,
        })
        groups = self.showcase.gl_gallery_groups()
        self.assertEqual([g['name'] for g in groups], ['Aufbau', 'Show', 'Weitere Fotos'])
        self.assertIn(photo, groups[0]['photos'])
        self.assertIn(photo, groups[1]['photos'])
        self.assertIn(extra, groups[2]['photos'])

        other_project = self.env['project.project'].create({'name': 'Fremde Galerie'})
        other_showcase = self.env['gl.project.showcase'].create({
            'name': 'Andere Galerie', 'project_id': other_project.id,
        })
        foreign_tag = photo_tag.create({
            'name': 'Nicht erlaubt', 'showcase_id': other_showcase.id,
        })
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                photo.write({'tag_ids': [fields.Command.link(foreign_tag.id)]})
        self.assertNotIn(foreign_tag, photo.tag_ids)

        # Names are unique within a showcase, not globally across customers.
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                photo_tag.create({'name': 'Aufbau', 'showcase_id': self.showcase.id})
        photo_tag.create({'name': 'Aufbau', 'showcase_id': other_showcase.id})

    def test_text_defaults_and_project_override(self):
        """Inherited text updates live; an explicit showcase value wins."""
        from ..models.texts import CONFIG_PREFIX, SHOWCASE_TEXTS
        params = self.env['ir.config_parameter'].sudo()
        key = CONFIG_PREFIX + 'hero_cta'
        old = params.get_param(key)
        try:
            self.assertIn('hero_cta', SHOWCASE_TEXTS)
            params.set_param(key, 'Die Highlights erleben')
            self.assertEqual(self.showcase.gl_get_texts()['hero_cta'], 'Die Highlights erleben')
            self.showcase.write({'gl_text_hero_cta': 'Hier klicken'})
            self.assertEqual(self.showcase.gl_get_texts()['hero_cta'], 'Hier klicken')
            params.set_param(key, 'Neuer Standard')
            self.assertEqual(self.showcase.gl_get_texts()['hero_cta'], 'Hier klicken')
            self.showcase.write({'gl_text_hero_cta': False})
            self.assertEqual(self.showcase.gl_get_texts()['hero_cta'], 'Neuer Standard')
        finally:
            params.set_param(key, old or '')

    def test_vimeo_oembed_thumbnail_cached_and_manual_override(self):
        """Fetch from Vimeo only, cache bytes locally, allow custom preferred image."""
        from io import BytesIO
        from unittest.mock import patch
        from PIL import Image
        from ..models import media

        output = BytesIO()
        Image.new('RGB', (16, 9), (26, 45, 83)).save(output, format='PNG')
        png = output.getvalue()

        class FakeResponse:
            status_code = 200
            content = b'{}'

            def json(self):
                return {'thumbnail_url': 'https://i.vimeocdn.com/video/123456_960.jpg'}

            def iter_content(self, chunk_size):
                return iter([png])

            def close(self):
                pass

        with patch.object(media.requests, 'get', side_effect=[FakeResponse(), FakeResponse()]) as req:
            video = self.env['gl.showcase.video'].create({
                'showcase_id': self.showcase.id,
                'name': 'Vimeo-Cover-Test',
                'vimeo_url': 'https://vimeo.com/123456',
            })
            self.assertEqual(req.call_count, 2)
            self.assertTrue(video.thumbnail_vimeo)
            self.assertTrue(video.thumbnail_checked_at)
            self.assertEqual(video.thumbnail_checked_url, video.vimeo_url)
            video._gl_sync_thumbnails()
            self.assertEqual(req.call_count, 2)  # Cached successful fetch

        # A customer-provided thumbnail can override the Vimeo one at any time.
        video.write({'thumbnail_custom': base64.b64encode(png)})
        self.assertTrue(video.thumbnail_custom)

    def test_unavailable_vimeo_thumbnail_does_not_block_video(self):
        from unittest.mock import patch
        from ..models import media
        with patch.object(media.requests, 'get', side_effect=media.requests.Timeout('offline')):
            video = self.env['gl.showcase.video'].create({
                'showcase_id': self.showcase.id,
                'name': 'Geschütztes Video',
                'vimeo_url': 'https://vimeo.com/5678',
            })
        self.assertTrue(video)
        self.assertFalse(video.thumbnail_vimeo)
        self.assertTrue(video.thumbnail_checked_at)
