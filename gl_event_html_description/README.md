# Groundlift Event HTML Description – Odoo 19

Version: **19.0.2.0.0**

## Behaviour

- Adds a brand-new field `event.event.gl_event_public_html` (`fields.Html`).
- Hides all occurrences of Odoo's standard `description` field in the assembled event form view.
- On install/upgrade, copies each existing event's current standard `description` HTML into the new field exactly once, including active-language translations.
- From then on, `gl_event_public_html` is the master value.
- Saving it mirrors its HTML into Odoo's standard `description` field so Odoo's native event website renders the new HTML without any QWeb template override.
- No website XPath/template inheritance is used.

## Upgrade from earlier variants

Replace the complete `gl_event_html_description` addon directory with this version and upgrade the module in Odoo. This version uses a new technical field name, so values from earlier experimental custom HTML fields are not reused.
