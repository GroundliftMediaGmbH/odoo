# Groundlift Event HTML Description (Odoo 19)

Small, isolated Odoo 19 module for `website_event`.

## What it does

- Adds a backend tab **Website HTML** to every event.
- On first installation, copies the existing Odoo event description into the new HTML source field for all existing events and active languages.
- New events initialize the field from Odoo's standard event description on creation.
- The public event page renders the new HTML source instead of `event.description`.
- The original Odoo description is not deleted or overwritten.

## Installation on Odoo.sh

1. Copy the folder `gl_event_html_description` into your custom addons repository.
2. Commit and push to the desired Odoo.sh branch.
3. Update the Apps list if needed.
4. Install **Groundlift Event HTML Description**.
5. Open an event and use the new **Website HTML** tab.

## Technical scope

Dependencies: only `website_event` and its standard dependencies.
No dependency on any Groundlift custom module.
