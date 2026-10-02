from urllib.parse import quote

from odoo import http, _
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale


class GroundliftEventCheckout(WebsiteSale):

    def _current_cart(self):
        return request.cart

    def _event_checkout_order_or_redirect(self):
        order = self._current_cart()
        if not order or order.state != "draft" or not order.order_line:
            return order, request.redirect("/shop/cart")
        return order, None

    @staticmethod
    def _is_checked(value):
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _is_supported_checkout_line(self, line):
        if line.display_type:
            return True
        if line.event_ticket_id:
            return True
        if getattr(line, "is_reward_line", False):
            return True
        if getattr(line, "reward_id", False):
            return True
        if getattr(line, "coupon_id", False):
            return True
        if line.price_total <= 0:
            return True
        return False

    def _get_checkout_line_groups(self, order):
        visible_lines = order.order_line.filtered(lambda l: not l.display_type)
        event_lines = visible_lines.filtered(lambda l: l.event_ticket_id)
        reward_lines = visible_lines - event_lines
        return event_lines, reward_lines

    @http.route(
        '/groundlift/event/<model("event.event"):event>/add_to_cart',
        type="http", auth="public", website=True, methods=["POST"], csrf=True, sitemap=False,
    )
    def groundlift_event_add_to_cart(self, event, **post):
        if not event.exists() or not event.is_published or not event.event_registrations_open:
            return request.redirect(event.website_url or "/event")
        if event.is_multi_slots:
            return request.redirect(f"/event/{request.env['ir.http']._slug(event)}/register")

        quantities = []
        for ticket in event.event_ticket_ids.sudo():
            raw = post.get(f"ticket_{ticket.id}", "0")
            try:
                qty = max(0, min(int(float(raw or 0)), 20))
            except (TypeError, ValueError):
                qty = 0
            if qty:
                quantities.append((ticket, qty))

        if not quantities:
            return request.redirect(f"{event.website_url}?ticket_error=choose")

        order = request.cart or request.website._create_cart()
        added_any = False
        for ticket, qty in quantities:
            if ticket.event_id != event or not ticket.is_launched or ticket.is_expired:
                continue
            result = order._cart_add(
                product_id=ticket.product_id.id,
                quantity=qty,
                event_ticket_id=ticket.id,
                event_slot_id=False,
            )
            if result.get("quantity", 0) or result.get("line_id"):
                added_any = True

        if not added_any:
            return request.redirect(f"{event.website_url}?ticket_error=unavailable")

        order.sudo().write({"meta_source_url": event.website_url})
        return request.redirect("/groundlift/checkout?added=1")

    @http.route('/groundlift/checkout', type="http", auth="public", website=True, sitemap=False)
    def groundlift_checkout(self, **kwargs):
        order, redirection = self._event_checkout_order_or_redirect()
        if redirection:
            return redirection

        if any(not self._is_supported_checkout_line(line) for line in order.order_line.filtered(lambda l: not l.display_type)):
            return request.redirect("/shop/checkout")

        order._recompute_cart()
        values = self._get_shop_payment_values(order, **kwargs)
        values.update(request.website._get_checkout_step_values())
        event_lines, reward_lines = self._get_checkout_line_groups(order)
        gl_has_newsletter_optin = "gl_cr_newsletter_optin" in order._fields
        values.update({
            "website_sale_order": order,
            "order": order,
            "only_services": True,
            "display_submit_button": True,
            "submit_button_label": _("Jetzt zahlen"),
            "gl_partner": order.partner_id if not order._is_anonymous_cart() else request.env["res.partner"],
            "gl_is_anonymous": order._is_anonymous_cart(),
            "gl_country": order.partner_id.country_id or request.env.ref("base.de", raise_if_not_found=False),
            "gl_order_lines": event_lines,
            "gl_reward_lines": reward_lines,
            "gl_has_newsletter_optin": gl_has_newsletter_optin,
            "gl_newsletter_optin": bool(getattr(order, "gl_cr_newsletter_optin", False)) if gl_has_newsletter_optin else False,
        })
        return request.render("groundlift_event_checkout.one_page_checkout", values)

    @http.route('/groundlift/checkout/customer', type="jsonrpc", auth="public", website=True, csrf=False)
    def groundlift_checkout_customer(self, **data):
        order = request.cart
        if not order or order.state != "draft":
            return {"ok": False, "error": _("Der Warenkorb ist nicht mehr verfügbar.")}

        first_name = (data.get("first_name") or "").strip()
        last_name = (data.get("last_name") or "").strip()
        email = (data.get("email") or "").strip()
        phone = (data.get("phone") or "").strip()
        zip_code = (data.get("zip") or "").strip()
        city = (data.get("city") or "").strip()
        newsletter_optin = self._is_checked(data.get("gl_cr_newsletter_optin"))
        missing = [label for value, label in [
            (first_name, _("Vorname")), (last_name, _("Nachname")),
            (email, _("E-Mail")), (phone, _("Telefon")),
            (zip_code, _("PLZ")), (city, _("Ort")),
        ] if not value]
        if missing:
            return {"ok": False, "error": _("Bitte ausfüllen: %s") % ", ".join(missing)}
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            return {"ok": False, "error": _("Bitte eine gültige E-Mail-Adresse eingeben.")}

        country = request.env.ref("base.de", raise_if_not_found=False)
        partner_vals = {
            "name": f"{first_name} {last_name}".strip(),
            "email": email,
            "phone": phone,
            "zip": zip_code,
            "city": city,
        }
        if country:
            partner_vals["country_id"] = country.id

        if order._is_anonymous_cart():
            partner_vals.update({
                "type": "contact",
                "company_id": order.website_id.company_id.id,
                "user_id": order.website_id.salesperson_id.id,
            })
            partner = request.env["res.partner"].sudo().with_context(tracking_disable=True).create(partner_vals)
            with request.env.protecting([order._fields["pricelist_id"]], order):
                order.sudo().write({
                    "partner_id": partner.id,
                    "partner_invoice_id": partner.id,
                    "partner_shipping_id": partner.id,
                })
            order.message_unsubscribe(order.website_id.partner_id.ids)
        else:
            partner = order.partner_id.sudo()
            partner.write(partner_vals)
            order.sudo().write({
                "partner_invoice_id": partner.id,
                "partner_shipping_id": partner.id,
            })

        order_vals = {
            "meta_first_name": first_name,
            "meta_last_name": last_name,
        }
        if "gl_cr_newsletter_optin" in order._fields:
            order_vals.update({
                "gl_cr_newsletter_optin": newsletter_optin,
                "gl_cr_newsletter_optin_source": "groundlift_event_checkout",
            })
        order.sudo().write(order_vals)
        request.session["sale_last_order_id"] = order.id
        return {"ok": True, "partner_id": partner.id}

    @http.route('/groundlift/checkout/line', type="http", auth="public", website=True,
                methods=["POST"], csrf=True, sitemap=False)
    def groundlift_checkout_line(self, line_id=None, action=None, **post):
        order = request.cart
        if not order or order.state != "draft":
            return request.redirect("/groundlift/checkout")
        try:
            line_id = int(line_id or 0)
        except (TypeError, ValueError):
            line_id = 0
        line = order.order_line.filtered(lambda l: l.id == line_id)[:1]
        if not line:
            return request.redirect("/groundlift/checkout")

        current_qty = int(round(line.product_uom_qty or 0))
        if action == "plus":
            new_qty = min(current_qty + 1, 99)
        elif action == "minus":
            new_qty = max(current_qty - 1, 0)
        elif action == "remove":
            new_qty = 0
        else:
            return request.redirect("/groundlift/checkout")

        update_kwargs = {}
        if line.event_ticket_id:
            update_kwargs["event_ticket_id"] = line.event_ticket_id.id
            update_kwargs["event_slot_id"] = line.event_slot_id.id or False

        order._cart_update_line_quantity(
            line_id=line.id,
            quantity=new_qty,
            **update_kwargs,
        )
        order._recompute_cart()
        remaining_tickets = order.order_line.filtered(lambda l: not l.display_type and l.event_ticket_id)
        if not remaining_tickets:
            request.website.sale_reset()
            return request.redirect("/event")
        return request.redirect("/groundlift/checkout")

    @http.route('/groundlift/checkout/coupon', type="http", auth="public", website=True,
                methods=["POST"], csrf=True, sitemap=False)
    def groundlift_checkout_coupon(self, coupon_code=None, **post):
        code = (coupon_code or post.get("promo") or "").strip()
        if not code:
            return request.redirect("/groundlift/checkout")
        return request.redirect(f"/coupon/{quote(code, safe='')}?r=/groundlift/checkout")

    @http.route('/groundlift/checkout/free_confirm', type="http", auth="public", website=True,
                methods=["POST"], csrf=True, sitemap=False)
    def groundlift_checkout_free_confirm(self, **post):
        order, redirection = self._event_checkout_order_or_redirect()
        if redirection:
            return redirection
        if order.amount_total:
            return request.redirect("/groundlift/checkout")
        if order._is_anonymous_cart():
            return request.redirect("/groundlift/checkout?customer_error=1")
        try:
            order._check_cart_is_ready_to_be_paid()
            order._validate_order()
        except (UserError, ValidationError):
            return request.redirect("/groundlift/checkout?validation_error=1")
        request.session["sale_last_order_id"] = order.id
        request.website.sale_reset()
        return request.redirect("/shop/confirmation")
