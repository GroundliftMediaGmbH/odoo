# Landingpage Text_to_HTML - v1.7

Upgrade repair for the obsolete inherited website view left in the database by v1.2-v1.5.

Runtime behavior:
- existing Groundlift text becomes editable HTML
- gl_landingpage_html is canonical
- Odoo event.description mirrors that HTML exactly
- the standard public Odoo event page therefore renders the HTML version
- the legacy QWeb inheritance record is rewritten to a harmless disabled no-op
