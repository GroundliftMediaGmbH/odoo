# Landingpage Text_to_HTML – Groundlift v1.6

This release deliberately removes all QWeb / website template inheritance.

## Behaviour

1. Groundlift's existing plain event text is converted to `gl_landingpage_html`.
2. `gl_landingpage_html` remains editable with Odoo's HTML editor.
3. The HTML field is canonical. Odoo's native `event.event.description` is kept
   as an exact mirror, so the standard public Odoo event page renders exactly
   the HTML version.
4. An old inherited website view from v1.2–v1.5 is disabled by a pre-migration
   script before module data is loaded. This avoids XPath ParseErrors on
   customized website_event templates.
5. If an inline website edit changes `event.description`, the change is mirrored
   back into `gl_landingpage_html` and the legacy plain-text field.

No `website_event` XPath is shipped in this package.
