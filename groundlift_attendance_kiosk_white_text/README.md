# Groundlift Attendance Kiosk – White Text (Odoo 19)

This small Odoo module improves text contrast on the public Attendance kiosk.
It changes only kiosk styles and does not alter employee data or attendance logic.

## Changed elements

- employee names on kiosk cards
- employee job titles
- department names in the sidebar
- kiosk clock/date and footer text
- preserves red/green attendance status colors
- preserves dark text inside the white search field

## Installation on Odoo.sh

1. Copy the folder `groundlift_attendance_kiosk_white_text` into the custom-addons repository.
2. Commit and push it to the desired Odoo.sh branch.
3. Wait for the build to finish.
4. Open Apps in Odoo and click **Update Apps List** if necessary.
5. Search for **Groundlift Attendance Kiosk – White Text** and install it.
6. Reload the kiosk with a hard refresh (`Ctrl+F5`).

## Upgrade after later changes

Upgrade the module from Apps, or run an Odoo update for:

`groundlift_attendance_kiosk_white_text`
