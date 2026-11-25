from odoo.fields import Command
from odoo.tests import TransactionCase, tagged
from ..models.account_tax import GL_GROSS_KEY


@tagged('post_install', '-at_install')
class TestFixedGross(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id
        cls.company.tax_calculation_rounding_method = 'round_globally'
        country = cls.company.account_fiscal_country_id or cls.company.country_id
        groups = cls.env['account.tax.group'].create([
            {'name': 'GL regression VAT %s' % rate,
             'company_id': cls.company.id, 'country_id': country.id}
            for rate in (19, 7)
        ])
        cls.tax19, cls.tax7 = cls.env['account.tax'].create([
            {'name': 'GL test VAT %s' % rate, 'amount': rate,
             'amount_type': 'percent', 'type_tax_use': 'sale',
             'price_include_override': 'tax_excluded',
             'company_id': cls.company.id, 'tax_group_id': group.id,
             'country_id': country.id}
            for rate, group in zip((19, 7), groups)
        ])

    def _line(self, gross, qty, tax, discount=0, marked=True):
        return self.env['account.tax']._prepare_base_line_for_taxes_computation(
            None, currency_id=self.currency, tax_ids=tax,
            price_unit=gross / (1 + tax.amount / 100), quantity=qty,
            discount=discount, computation_key=GL_GROSS_KEY if marked else False,
        )

    def _compute(self, lines):
        engine = self.env['account.tax']
        engine._add_tax_details_in_base_lines(lines, self.company)
        engine._round_base_lines_tax_details(lines, self.company)
        return engine._get_tax_totals_summary(lines, self.currency, self.company)

    def test_product_net_is_precise(self):
        self.company.tax_calculation_rounding_method = 'round_per_line'
        product = self.env['product.template'].create({
            'name': 'GL test Tegernseer', 'company_id': self.company.id,
            'taxes_id': [Command.set(self.tax19.ids)], 'gross_list_price': 3.60,
        })
        self.assertAlmostEqual(product.list_price, 3.60 / 1.19, delta=0.000001)
        product.action_gl_reapply_gross_price()
        product.flush_recordset(["list_price", "gross_list_price"])
        product.invalidate_recordset(["list_price", "gross_list_price"])
        self.assertAlmostEqual(product.list_price, 3.60 / 1.19, delta=0.000001)
        self.assertAlmostEqual(product.gross_list_price, 3.60, places=2)

    def test_groundlift_cart_global(self):
        lines = [self._line(3.60, 36, self.tax19), self._line(3.00, 8, self.tax19),
                 self._line(0.70, 3, self.tax7), self._line(4.50, 19, self.tax19)]
        summary = self._compute(lines)
        self.assertAlmostEqual(summary['total_amount_currency'], 241.20, places=2)
        self.assertAlmostEqual(summary['tax_amount_currency'], 38.32, places=2)
        self.assertAlmostEqual(summary['base_amount_currency'], 202.88, places=2)
        for line, expected in zip(lines, (129.60, 24, 2.10, 85.50)):
            self.assertAlmostEqual(line['tax_details']['total_included_currency'], expected, places=2)
            self.assertEqual(line['tax_details']['delta_total_excluded_currency'], 0)
            self.assertEqual(self.env['account.tax']._export_base_line_extra_tax_data(line)['computation_key'], GL_GROSS_KEY)

    def test_quantities_and_refund(self):
        for method in ('round_globally', 'round_per_line'):
            self.company.tax_calculation_rounding_method = method
            for qty in (1, 2, 3, 36, 100, -36):
                line = self._line(3.60, qty, self.tax19)
                summary = self._compute([line])
                self.assertAlmostEqual(summary['total_amount_currency'], 3.60 * qty, places=2)

    def test_split_and_discount(self):
        lines = [self._line(3.60, 1, self.tax19) for _ in range(36)]
        summary = self._compute(lines)
        self.assertAlmostEqual(summary['total_amount_currency'], 129.60, places=2)
        for line in lines:
            self.assertAlmostEqual(line['tax_details']['total_included_currency'], 3.60, places=2)
        line = self._line(3.60, 36, self.tax19, discount=10)
        self.assertAlmostEqual(self._compute([line])['total_amount_currency'], 116.64, places=2)

    def test_unmarked_price_uses_standard_engine(self):
        line = self._line(3.60, 1, self.tax19, marked=False)
        self._compute([line])
        self.assertFalse(line.get('_gl_fixed_gross_computed'))
