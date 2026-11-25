"""Server-side PDF rasterisation for preview-only attachments.

Browser receives one JPEG image per page, never the original PDF.
Requires pypdfium2 in the Odoo.sh repository requirements.txt.
No native/system package (poppler) is required.
"""
from io import BytesIO
import importlib
from math import sqrt


MAX_PAGES = 120
MAX_RENDER_PIXELS = 3_000_000
MAX_RENDER_DIMENSION = 2100


class PdfPreviewError(Exception):
    pass


def _load_pdfium():
    """Lazy dependency loading avoids breaking the entire Odoo registry.

    Odoo.sh only installs pypdfium2 if requirements.txt was committed in
    the Git repository. Missing native/pdfium binaries must NEVER prevent
    Odoo from starting or allow the unprotected original PDF to be served.
    """
    try:
        return importlib.import_module('pypdfium2')
    except (ImportError, OSError) as exc:
        raise PdfPreviewError(
            'PDF-Vorschau nicht verfügbar: pypdfium2 fehlt oder kann nicht geladen werden. '
            'Bitte requirements.txt im Git-Repository prüfen.'
        ) from exc


def count_pdf_pages(pdf_data):
    try:
        with _load_pdfium().PdfDocument(pdf_data) as pdf:
            n = len(pdf)
            if n < 1 or n > MAX_PAGES:
                raise PdfPreviewError('PDF enthält keine Seiten oder überschreitet das Limit von %s Seiten.' % MAX_PAGES)
            return n
    except PdfPreviewError:
        raise
    except Exception as exc:
        raise PdfPreviewError('PDF konnte nicht geöffnet werden.') from exc


def render_pdf_page(pdf_data, page_num):
    """Return rendered JPEG bytes (1-based page); constrained size and pixels."""
    try:
        with _load_pdfium().PdfDocument(pdf_data) as pdf:
            n = len(pdf)
            if n < 1 or n > MAX_PAGES or not 1 <= page_num <= n:
                raise PdfPreviewError('Ungültige PDF-Seite.')
            page = pdf[page_num - 1]
            try:
                width, height = page.get_size()
                if width <= 0 or height <= 0 or width * height > 100_000_000:
                    raise PdfPreviewError('Ungültige PDF-Seitengröße.')
                scale = min(2.0, MAX_RENDER_DIMENSION / max(width, height),
                            sqrt(MAX_RENDER_PIXELS / (width * height)))
                bitmap = page.render(scale=scale)
                try:
                    picture = bitmap.to_pil().convert('RGB')
                    stream = BytesIO()
                    picture.save(stream, format='JPEG', quality=83, optimize=True)
                    return stream.getvalue()
                finally:
                    bitmap.close()
            finally:
                page.close()
    except PdfPreviewError:
        raise
    except Exception as exc:
        raise PdfPreviewError('PDF-Seite konnte nicht gerendert werden.') from exc
