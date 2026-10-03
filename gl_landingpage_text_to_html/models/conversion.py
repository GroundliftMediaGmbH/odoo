"""Small, independent text/HTML converters for the Groundlift event description.

HTML escaping happens *before* generating <br/> tags.  HTML sanitizing is left
in the hands of Odoo's fields.Html implementation.
"""

from html import escape
import re
from lxml import html as lxml_html


def plain_to_html(value):
    """Represent existing newlines visually exactly, without interpreting markup."""
    if not value:
        return ''
    value = str(value).replace('\r\n', '\n').replace('\r', '\n')
    return escape(value, quote=True).replace('\n', '<br/>')


def html_to_plain(value):
    """Keep readable paragraph boundaries when the editor saves rich content."""
    if not value:
        return ''
    try:
        root = lxml_html.fragment_fromstring(value, create_parent='div')
    except (TypeError, ValueError):
        return str(value)
    output = []
    blocks = {'p', 'div', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'pre'}

    def walk(node):
        if node.text:
            output.append(node.text)
        for child in node:
            tag = str(child.tag).lower() if isinstance(child.tag, str) else ''
            if tag == 'br':
                output.append('\n')
            else:
                if tag == 'li':
                    output.append('- ')
                walk(child)
                if tag in blocks:
                    output.append('\n')
            if child.tail:
                output.append(child.tail)

    walk(root)
    content = ''.join(output).replace('\xa0', ' ')
    content = re.sub(r'[ \t]+\n', '\n', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip('\n')
