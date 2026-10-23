"""Odoo.sh tests for multi-upload, optional captions and scoped bulk edits."""
import base64
from io import BytesIO

from PIL import Image

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


def png_bytes(color):
    output = BytesIO()
    Image.new('RGB', (24, 16), color).save(output, format='PNG')
    return output.getvalue()


PDF_BYTES = b'%PDF-1.7\n1 0 obj\nendobj\n%%EOF'


class TestShowcaseMediaBatch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({'name': 'Massenmedien Test'})
        cls.showcase = cls.env['gl.project.showcase'].create({
            'project_id': cls.project.id, 'name': 'Mehrfachupload Test',
            'website_id': cls.env['website'].search([], limit=1).id,
        })
        cls.tag = cls.env['gl.showcase.photo.tag'].create({
            'showcase_id': cls.showcase.id, 'name': 'Bühne',
        })

    def _wizard(self, kind='photo', mode='upload', **extra):
        return self.env['gl.showcase.media.batch.wizard'].create({
            'showcase_id': self.showcase.id, 'media_kind': kind, 'mode': mode,
            **extra,
        })

    def _attachment(self, wizard, name, payload):
        return self.env['ir.attachment'].create({
            'name': name, 'type': 'binary', 'datas': base64.b64encode(payload),
            'res_model': wizard._name, 'res_id': wizard.id,
        })

    def test_batch_upload_photos_with_optional_caption(self):
        wizard = self._wizard(tag_ids=[(6, 0, [self.tag.id])])
        a = self._attachment(wizard, 'Erster_Shot.png', png_bytes('#dbf8ff'))
        b = self._attachment(wizard, 'Zweiter_Shot.png', png_bytes('#ffdcaa'))
        wizard.write({'attachment_ids': [(6, 0, [a.id, b.id])]})
        self.assertEqual(wizard.action_apply()['type'], 'ir.actions.act_window_close')
        self.assertEqual(len(self.showcase.photo_ids), 2)
        self.assertEqual(set(self.showcase.photo_ids.mapped('name')), {'Erster Shot', 'Zweiter Shot'})
        for photo in self.showcase.photo_ids:
            self.assertFalse(photo.description)
            self.assertEqual(photo.tag_ids, self.tag)
            self.assertTrue(photo.photo)
        self.assertFalse(a.exists())
        self.assertFalse(b.exists())

    def test_batch_edit_photo_selective_title_and_tags(self):
        other = self.env['gl.showcase.photo.tag'].create({
            'showcase_id': self.showcase.id, 'name': 'Backstage',
        })
        picture = base64.b64encode(png_bytes('#12abcd'))
        first, second, untouched = self.env['gl.showcase.photo'].create([
            {'showcase_id': self.showcase.id, 'name': 'Alt 1', 'photo': picture, 'description': 'Wichtig'},
            {'showcase_id': self.showcase.id, 'name': 'Alt 2', 'photo': picture},
            {'showcase_id': self.showcase.id, 'name': 'Anderes Bild', 'photo': picture},
        ])
        wizard = self._wizard(mode='edit', photo_ids=[(6, 0, [first.id, second.id])],
                              edit_name=True, name='Showbild', tag_mode='add',
                              tag_ids=[(6, 0, [self.tag.id, other.id])])
        wizard.action_apply()
        self.assertEqual(first.name, 'Showbild')
        self.assertEqual(second.name, 'Showbild')
        self.assertEqual(first.description, 'Wichtig')  # Not overwritten.
        self.assertEqual(first.tag_ids, self.tag | other)
        self.assertEqual(untouched.name, 'Anderes Bild')
        self.assertFalse(untouched.tag_ids)
        clearing = self._wizard(mode='edit', all_items=True, edit_description=True,
                                tag_mode='replace')
        clearing.action_apply()
        self.assertFalse(first.description)
        self.assertFalse(first.tag_ids)
        self.assertFalse(second.tag_ids)

    def test_batch_upload_docs_with_tags_and_download_policy(self):
        wizard = self._wizard(kind='document', name='Kundenfreigabe',
                              tag_ids=[(6, 0, [self.tag.id])])
        files = [self._attachment(wizard, '01.pdf', PDF_BYTES),
                 self._attachment(wizard, '02.pdf', PDF_BYTES)]
        wizard.write({'attachment_ids': [(6, 0, [f.id for f in files])]})
        wizard.action_apply()
        self.assertEqual(len(self.showcase.document_ids), 2)
        for doc in self.showcase.document_ids:
            self.assertEqual(doc.name, 'Kundenfreigabe')
            self.assertEqual(doc.tag_ids, self.tag)
            self.assertTrue(doc.has_preview)
            self.assertFalse(doc.allow_download)
        bulk = self._wizard(kind='document', mode='edit', all_items=True,
                            edit_name=True, name='Finale Version',
                            tag_mode='replace', tag_ids=[(6, 0, [self.tag.id])])
        bulk.action_apply()
        self.assertEqual(set(self.showcase.document_ids.mapped('name')), {'Finale Version'})
        self.assertTrue(all(doc.tag_ids == self.tag for doc in self.showcase.document_ids))

    def test_no_partial_upload_if_invalid_file_and_no_download(self):
        wizard = self._wizard(kind='document')
        good = self._attachment(wizard, 'gut.pdf', PDF_BYTES)
        bad = self._attachment(wizard, 'nicht_erlaubt.docx', b'PK\x03\x04notreallydocx')
        wizard.write({'attachment_ids': [(6, 0, [good.id, bad.id])]})
        with self.assertRaises(ValidationError):
            wizard.action_apply()
        self.assertFalse(self.showcase.document_ids)
        self.assertTrue(good.exists())

    def test_scope_guards_on_tags_and_selection(self):
        foreign_project = self.env['project.project'].create({'name': 'Fremd'})
        foreign = self.env['gl.project.showcase'].create({
            'project_id': foreign_project.id, 'name': 'Fremdes Showcase',
        })
        tag = self.env['gl.showcase.photo.tag'].create({
            'showcase_id': foreign.id, 'name': 'Fremdtag',
        })
        wizard = self._wizard(tag_ids=[(6, 0, [tag.id])])
        with self.assertRaises(ValidationError):
            wizard.action_apply()
        photo = self.env['gl.showcase.photo'].create({
            'showcase_id': foreign.id, 'name': 'Geheim',
            'photo': base64.b64encode(png_bytes('#abcdef')),
        })
        editing = self._wizard(mode='edit', edit_name=True, name='Nicht erlaubt',
                               photo_ids=[(6, 0, [photo.id])])
        with self.assertRaises(ValidationError):
            editing.action_apply()
        self.assertEqual(photo.name, 'Geheim')

    def test_action_defaults_for_document_and_video(self):
        video = self.env['gl.showcase.video'].create({
            'showcase_id': self.showcase.id,
            'name': 'Clip', 'vimeo_url': 'https://vimeo.com/999777',
        })
        action = video.action_gl_upload_video_documents()
        self.assertEqual(action['context']['default_video_id'], video.id)
        self.assertEqual(action['context']['default_media_kind'], 'document')
        self.assertEqual(self.showcase.action_gl_upload_photos()['context']['default_mode'], 'upload')
