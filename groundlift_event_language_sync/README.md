# Groundlift Event Language Sync (Odoo 19)

Technical Odoo 19 module for `event.event`.

## Purpose

Odoo stores values of fields with `translate=True` per language. This module makes
German (`de_DE`) and English (`en_US`) behave like two language views of the same
event content.

## Behaviour

- On installation, all existing events are synchronized once from German to English.
- Afterwards, every create/write on `event.event` in German or English mirrors the
  changed translated fields to the other language.
- The translated field list is determined dynamically from the Odoo registry.
  Therefore translated fields added by other installed modules or by Odoo Studio
  are included automatically.
- Non-translated fields are untouched.
- Related fields and non-writable computed translated fields are skipped for safety.
- No menus, views or existing event workflows are changed.

## Installation on Odoo.sh

1. Copy the folder `groundlift_event_language_sync` into your custom addons repository.
2. Commit and push to the Odoo.sh branch.
3. Update the Apps list if needed.
4. Install **Groundlift Event Language Sync**.

The installation performs the one-time synchronization of existing events automatically.
