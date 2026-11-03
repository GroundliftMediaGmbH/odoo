"""Card color options must not change the existing design until configured."""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestShowcaseCardColors(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        project = cls.env['project.project'].create({'name': 'Showcase card colors'})
        cls.showcase = cls.env['gl.project.showcase'].create({
            'name': 'Color test',
            'project_id': project.id,
            'website_id': cls.env['website'].search([], limit=1).id,
        })

    def test_unset_preserves_original_css(self):
        css = self.showcase.gl_css_variables
        self.assertIn('--gl-bg:', css)
        self.assertNotIn('--gl-video-card-bg:', css)
        self.assertNotIn('--gl-document-card-bg:', css)

    def test_independent_video_and_document_colors(self):
        self.showcase.write({
            'color_video_card': '#261845',
            'color_video_text': '#FFFFFF',
            'color_video_border': '#534080',
            'color_document_card': '#172433',
            'color_document_text': '#EFEFEF',
            'color_document_border': '#456789',
        })
        css = self.showcase.gl_css_variables
        for setting in ('--gl-video-card-bg: #261845', '--gl-video-card-fg: #FFFFFF',
                        '--gl-video-card-border: #534080', '--gl-document-card-bg: #172433',
                        '--gl-document-card-fg: #EFEFEF', '--gl-document-card-border: #456789'):
            self.assertIn(setting, css)
        self.showcase.color_document_card = False
        self.assertNotIn('--gl-document-card-bg:', self.showcase.gl_css_variables)

    def test_invalid_hex_rejected(self):
        with self.assertRaises(ValidationError):
            self.showcase.color_video_card = '#GGGGGG'
