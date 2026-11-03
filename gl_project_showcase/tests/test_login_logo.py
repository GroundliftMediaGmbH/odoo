"""Regression: the optional login logo is visible before password entry only.

The public controller endpoint is exercised without granting a valid session;
all other showcase branding remains protected.
"""
import base64
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from odoo.tests.common import TransactionCase

from ..controllers import main
from ..models.media import decode_record_file, safe_mime


class TestLoginLogo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        project = cls.env['project.project'].create({'name': 'Login logo test project'})
        cls.showcase = cls.env['gl.project.showcase'].create({
            'project_id': project.id, 'name': 'Login logo test',
        })
        buffer = BytesIO()
        Image.new('RGBA', (24, 12), (128, 80, 30, 255)).save(buffer, format='PNG')
        cls.png = base64.b64encode(buffer.getvalue())

    def _call_logo_endpoint(self):
        controller = main.ShowcaseController()
        with patch.object(controller, '_show', return_value=self.showcase), \
                patch.object(controller, '_binary_response', return_value='IMAGE') as send, \
                patch.object(main, 'request') as req:
            req.not_found.return_value = 'NOT_FOUND'
            outcome = controller.showcase_login_logo(self.showcase.id)
            args = send.call_args.args if send.call_args else None
            return outcome, args

    def test_upload_optional_and_kept_separate_from_client_logo(self):
        self.assertFalse(self.showcase.password_logo)
        self.showcase.write({'password_logo': self.png})
        self.assertFalse(self.showcase.logo)
        self.assertEqual(safe_mime(decode_record_file(self.showcase, 'password_logo')), 'image/png')

    def test_login_logo_endpoint_never_reveals_draft_or_private_page(self):
        self.showcase.password_logo = self.png
        self.assertEqual(self._call_logo_endpoint()[0], 'NOT_FOUND')
        self.showcase._set_new_password('TestPasswort-2026!')
        self.showcase.write({'visibility': 'password', 'published': True})
        result, args = self._call_logo_endpoint()
        self.assertEqual(result, 'IMAGE')
        self.assertTrue(args[0].startswith(b'\x89PNG'))
        self.assertEqual(args[2], 'image/png')
        self.showcase.visibility = 'private'
        self.assertEqual(self._call_logo_endpoint()[0], 'NOT_FOUND')
        self.showcase.visibility = 'password'
        self.showcase.published = False
        self.assertEqual(self._call_logo_endpoint()[0], 'NOT_FOUND')

    def test_missing_login_logo_does_not_leak_regular_logo(self):
        self.showcase.logo = self.png
        self.showcase._set_new_password('TestPasswort-2026!')
        self.showcase.write({'visibility': 'password', 'published': True})
        result, args = self._call_logo_endpoint()
        self.assertEqual(result, 'NOT_FOUND')
        self.assertIsNone(args)
        controller = main.ShowcaseController()
        with patch.object(controller, '_show', return_value=self.showcase), \
                patch.object(controller, '_is_allowed', return_value=False), \
                patch.object(main, 'request') as req:
            req.not_found.return_value = 'NOT_FOUND'
            self.assertEqual(controller.showcase_brand(self.showcase.id, 'logo'), 'NOT_FOUND')

    def test_image_format_allowlist_rejects_non_image_payload(self):
        self.showcase._set_new_password('TestPasswort-2026!')
        self.showcase.write({'visibility': 'password', 'published': True})
        with patch.object(main, 'decode_record_file', return_value=b'<svg>not a supported image</svg>'):
            self.assertEqual(self._call_logo_endpoint()[0], 'NOT_FOUND')
