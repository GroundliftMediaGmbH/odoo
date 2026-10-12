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
