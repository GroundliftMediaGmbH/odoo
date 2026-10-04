# Groundlift Event Register Redirect

Odoo 19 SH addon for one targeted redirect.

## Source

`/event/susanne-kirchland-band-celebration-concert-94/register`

## Target

`https://groundlift.odoo.com/odoo/events/94/website`

The addon uses HTTP status **302** intentionally, which is safer for staging/testing because browsers and proxies should not treat the mapping as permanent.

## Installation on Odoo SH

1. Copy the folder `gl_event_register_redirect` into the repository's addons/custom-addons location used by your project.
2. Commit and push it to the staging branch.
3. In Odoo, update the Apps list if necessary.
4. Search for **Groundlift Event Register Redirect** and install it.
5. Open the source URL in a private/incognito window to verify the redirect.

Dependency: `website_event`.
