from odoo import api, models


class EventEventTicket(models.Model):
    _inherit = "event.event.ticket"

    def _gl_expected_exact_product_net(self, product=None):
        """Return exact net implied by a Groundlift-managed product gross price.

        This deliberately only applies when the linked product template is
        explicitly marked as Groundlift gross-price-managed. Standard Odoo
        event tickets remain untouched.
        """
        self.ensure_one()
        product = product or self.product_id
        if not product:
            return None

        template = product.product_tmpl_id
        if not template.gl_gross_price_managed:
            return None

        company = self.company_id or self.env.company
        template = template.with_company(company)
        return template._gl_exact_net_from_gross(template.gross_list_price or 0.0)

    def _gl_normalize_ticket_net_value(self, value, product=None):
        """Recover exact net when Odoo/UI has reduced it to currency cents.

        Example with 7% VAT:
            gross product price = 12.00
            exact net           = 11.214953271...
            UI-rounded net      = 11.21
            11.21 * 1.07        = 11.9947 -> 11.99

        If the incoming ticket net is exactly the currency-rounded form of the
        exact product net, restore the exact value. Values which genuinely
        differ from the product price are not modified.
        """
        self.ensure_one()
        product = product or self.product_id
        expected = self._gl_expected_exact_product_net(product=product)
        if expected is None:
            return value

        company = self.company_id or self.env.company
        currency = self.currency_id or company.currency_id

        try:
            incoming = float(value)
        except (TypeError, ValueError):
            return value

        rounded_expected = currency.round(expected)

        # Only repair the very specific precision-loss pattern. This means a
        # genuinely different manually configured event-ticket price remains
        # untouched.
        if currency.compare_amounts(incoming, rounded_expected) == 0:
            return expected

        return value

    @api.model_create_multi
    def create(self, vals_list):
        # product_id/company_id are not records yet in `self`, so create first
        # and then normalize only tickets that received an explicit price.
        tickets = super().create(vals_list)
        for ticket, vals in zip(tickets, vals_list):
            if "price" not in vals:
                continue
            normalized = ticket._gl_normalize_ticket_net_value(ticket.price)
            if normalized != ticket.price:
                super(EventEventTicket, ticket.with_context(
                    gl_skip_event_ticket_net_normalize=True
                )).write({"price": normalized})
        return tickets

    def write(self, vals):
        if self.env.context.get("gl_skip_event_ticket_net_normalize"):
            return super().write(vals)

        vals = dict(vals)
        if "price" in vals and len(self) == 1:
            ticket = self
            product = (
                self.env["product.product"].browse(vals["product_id"])
                if vals.get("product_id")
                else ticket.product_id
            )
            vals["price"] = ticket._gl_normalize_ticket_net_value(
                vals["price"],
                product=product,
            )

        result = super().write(vals)

        # Multi-record writes or a product switch can only be normalized safely
        # after the write, because each ticket can have a different product /
        # company / currency.
        if "price" in vals and len(self) > 1:
            for ticket in self:
                normalized = ticket._gl_normalize_ticket_net_value(ticket.price)
                if normalized != ticket.price:
                    super(EventEventTicket, ticket.with_context(
                        gl_skip_event_ticket_net_normalize=True
                    )).write({"price": normalized})

        return result

    def _gl_repair_rounded_net_from_managed_product(self):
        """Repair already affected tickets conservatively.

        Only changes a ticket when its current net price is the currency-rounded
        representation of the exact net implied by its managed product gross
        price. A ticket with a genuinely different price is left unchanged.
        """
        repaired = 0
        for ticket in self:
            normalized = ticket._gl_normalize_ticket_net_value(ticket.price)
            if normalized != ticket.price:
                super(EventEventTicket, ticket.with_context(
                    gl_skip_event_ticket_net_normalize=True
                )).write({"price": normalized})
                repaired += 1
        return repaired
