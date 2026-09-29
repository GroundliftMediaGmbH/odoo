# Groundlift Event Location Label – Odoo 19

Small Odoo 19 module for Groundlift.

## What it does

On public Odoo event pages, the technical timezone label such as:

`Europe/Berlin`

is replaced by:

`Inning am Ammersee`

This applies to:

- normal one-day events
- multi-day events
- multi-slot events
- desktop and mobile event pages
- all website languages

## Important

The module changes **only the visible label**. It does **not** change the
configured event timezone (`event.date_tz`). Odoo therefore still uses the
correct timezone for event times and calendar links.

## Installation on Odoo.sh

1. Copy the folder `groundlift_event_location_label` into your Git repository.
2. Commit and push it to the desired Odoo.sh branch.
3. In Odoo, update the Apps list.
4. Search for **Groundlift Event Location Label**.
5. Install the module.
6. Hard-refresh an event page if the browser still shows cached content.

## Change the displayed text later

Edit `views/event_templates.xml` and replace every occurrence of:

`Inning am Ammersee`

with the desired label, then upgrade the module.
