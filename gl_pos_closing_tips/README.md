# Groundlift POS Closing Tips for Odoo 19 SH

Displays native POS tips as **informational amounts** in the register closing popup.

## Installation
1. Add `gl_pos_closing_tips` to your custom addons repository.
2. Update Apps list, install **Groundlift POS Closing Tips**.
3. Reload the POS completely (close and reopen POS browser tab).

## Behaviour
- Totals native `pos.order.tip_amount` of paid/done/invoiced orders in the active session; fallback to configured tip-product order lines when `tip_amount` is unavailable/zero.
- Classifies tip as cash only when all payment methods for that order have `is_cash_count=True`.
- Noncash includes card and other non-cash payment methods; the value is not guaranteed to be card-only.
- Splits involving cash and noncash are shown separately as not uniquely attributable.
- Read-only UI: does not change settlement, totals, accounting entries, cash difference, or tip taxation.

## Important staging checklist
Odoo POS component DOM and store structure can change. This implementation uses a conservative DOM extension rather than changing internal Odoo closing methods. Verify on staging against your exact Odoo 19 build: closing popup title detection, visible rows, active session ID, reload, and closing without regression. If the lines do not appear, request JS console output. This archive is syntax-checked locally, **not** verified against a running Odoo SH server.
