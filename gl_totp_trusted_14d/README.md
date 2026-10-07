# Groundlift - 2FA trusted devices (14 days)

Odoo 19 SH addon for reducing repeated TOTP prompts without disabling 2FA.

## Behaviour

- 2FA/TOTP remains enabled.
- After a successful TOTP login, the current browser/device is automatically marked as trusted.
- The trust expires after exactly 14 days.
- During those 14 days, subsequent password logins from the same browser/device can skip the TOTP challenge.
- A different browser/device must complete 2FA once before it receives its own 14-day trust.
- Incognito/private browsing, clearing cookies, changing browser profiles, or revoking trusted devices forces 2FA again.
- Changing the user's password already revokes trusted devices in Odoo's standard `auth_totp` module.

## Installation effect

On first installation, existing Odoo trusted-device grants are revoked once. This is intentional so old grants created with Odoo's default lifetime do not remain valid longer than 14 days. Existing active sessions are not forcibly logged out.

## Important: session timeouts are separate

This module controls the *second factor*, not Odoo's session/inactivity timeout.
If users are still asked for username/password several times per hour, check whether the Odoo `auth_timeout` module is installed and whether a group has a short inactivity/session timeout configured.

Odoo 19 path:

**Settings -> Users & Companies -> Groups -> [group] -> Timeouts**

For a normal internal Groundlift workstation/mobile workflow, avoid a policy such as "Logout with two-factor authentication" every few minutes/hours unless that is explicitly required.

## Install on Odoo.sh

1. Copy the folder `gl_totp_trusted_14d` into the custom-addons repository.
2. Commit and push to the staging branch.
3. In Odoo: Apps -> Update Apps List.
4. Search for `Groundlift - 2FA trusted devices (14 days)` and install it.
5. Test with one user before deploying to production.

## Test

1. Open Odoo in a normal browser window.
2. Log out and log in again.
3. Enter password and complete TOTP once.
4. Log out again.
5. Log in again in the same browser/profile: TOTP should be skipped.
6. Test from a new/incognito browser: TOTP must be required.

