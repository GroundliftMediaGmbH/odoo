# Landingpage Text_to_HTML – Groundlift – v1.5

This build intentionally returns to the v1.2 model/mirroring logic and changes only the public website rendering path:

- Existing Groundlift plain event text is mirrored into `gl_landingpage_html`.
- `gl_landingpage_html` remains editable with Odoo's HTML editor.
- Edits are mirrored back to the existing plain-text field as in v1.2.
- The public Odoo event page replaces the native `event.description` node with `gl_landingpage_html` only.
- There is **no website fallback** to `event.description`.
- The website XPath deliberately targets only the `t-field="event.description"` node, without depending on its surrounding Odoo DOM structure.

The upgrade migration preserves existing rich HTML and only fills empty HTML fields.
