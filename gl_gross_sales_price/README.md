# Groundlift Bruttopreis Eingabe – Odoo 19

Version **19.0.1.3.0**

## Fix in v1.3

v1.2 kept the exact tax-exclusive product price, but Odoo 19 POS still
aggregated and redistributed tax cents across the whole basket.

Example:
- customer-facing gross lines: 56.00 EUR
- exact 7% + 19% tax groups under global redistribution: 5.21 EUR tax
- rounded tax-exclusive bases: 50.78 EUR
- Odoo POS total: 55.99 EUR

v1.3 keeps the company setting unchanged (`round_globally`) and applies
`round_per_line` **only to POS tax base lines whose product is marked
`gl_gross_price_managed`**.

The same rule is applied:
- in the POS browser calculation,
- on the POS server calculation,
- during POS session accounting,
- and propagated to invoices created from those POS lines.

Normal products and non-POS documents keep the company's normal rounding rule.

## Upgrade

1. Replace the existing `gl_gross_sales_price` folder with this version.
2. Upgrade the app in Odoo.
3. Reload/reopen the POS so the new asset bundle is loaded.
4. Recreate the 56.00 EUR test basket.

Expected result:
- Taxes: 5.22 EUR
- Total: 56.00 EUR
