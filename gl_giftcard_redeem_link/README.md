# Groundlift Gift Card Redeem Link (Odoo 19)

This module changes the final rendered URL of the standard Odoo 19 gift-card email button from the Odoo `/shop` URL to:

`https://groundlift.de/public-events.php`

## Why it works

Odoo's standard template `loyalty.mail_template_gift_card` contains a dynamic QWeb link based on `object.get_base_url() + /shop`. Even if a normal `href` is edited in the visual template editor, the dynamic QWeb attribute can still win during rendering.

This module leaves the editable email template and its design untouched. After Odoo has rendered the gift-card email, it rewrites only `/shop` hrefs in that specific standard gift-card template.

## Installation on Odoo.sh

1. Copy the folder `gl_giftcard_redeem_link` into the repository's custom addons directory.
2. Commit and push to the desired Odoo.sh branch.
3. Wait for the build.
4. In Odoo, update the Apps list if necessary.
5. Search for **Groundlift Gift Card Redeem Link** and install it.
6. Generate a new gift card and send a new test email.

No configuration is required.
