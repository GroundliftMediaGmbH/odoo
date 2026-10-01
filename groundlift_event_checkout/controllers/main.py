import json

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

    @http.route(
        '/groundlift/event/<model("event.event"):event>/add_to_cart',
        type="http", auth="public", website=True, methods=["POST"], csrf=True, sitemap=False,
    )
    def groundlift_event_add_to_cart(self, event, **post):
        if not event.exists() or not event.is_published or not event.event_registrations_open:
            return request.redirect(event.website_url or "/event")
        if event.is_multi_slots:
            # Multi-slot events keep Odoo's standard registration flow because a slot
            # is an additional required cart dimension.
            return request.redirect(f"/event/{request.env['ir.http']._slug(event)}/register")

        quantities = []
        for ticket in event.event_ticket_ids.sudo():
            raw = post.get(f"ticket_{ticket.id}", "0")
            try:
                qty = max(0, min(int(raw or 0), 20))
            except (TypeError, ValueError):
                qty = 0
            if qty:
                quantities.append((ticket, qty))

        if not quantities:
            return request.redirect(f"{event.website_url}?ticket_error=choose")

        order = request.cart or request.website._create_cart()
        added_any = False
        for ticket, qty in quantities:
            # _cart_add/_verify_updated_quantity remains the authority for current
            # seat availability and prevents overselling.
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

        # Keep context for a clean back-link and for Meta/CAPI event_source_url.
        order.sudo().write({"meta_source_url": event.website_url})
        return request.redirect("/groundlift/checkout?added=1")

    @http.route('/groundlift/checkout', type="http", auth="public", website=True, sitemap=False)
    def groundlift_checkout(self, **kwargs):
        order, redirection = self._event_checkout_order_or_redirect()
        if redirection:
            return redirection

        # This module is intended for event tickets. If another product was mixed
        # into the cart, fall back to Odoo's standard flow rather than bypassing
        # delivery/address logic for physical goods.
        if any(not line.event_ticket_id for line in order.order_line.filtered(lambda l: not l.display_type)):
            return request.redirect("/shop/checkout")

        order._recompute_cart()
        values = self._get_shop_payment_values(order, **kwargs)
        values.update(request.website._get_checkout_step_values())
        values.update({
            "website_sale_order": order,
            "order": order,
            "only_services": True,
            "display_submit_button": True,
            "submit_button_label": _("Jetzt zahlen"),
            "gl_partner": order.partner_id if not order._is_anonymous_cart() else request.env["res.partner"],
            "gl_is_anonymous": order._is_anonymous_cart(),
            "gl_country": order.partner_id.country_id or request.env.ref("base.de", raise_if_not_found=False),
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
            # Protect the already accepted website pricelist while changing the public partner.
            with request.env.protecting([order._fields["pricelist_id"]], order):
                order.sudo().write({
                    "partner_id": partner.id,
                    "partner_invoice_id": partner.id,
                    "partner_shipping_id": partner.id,
                })
            order.message_unsubscribe(order.website_id.partner_id.ids)
        else:
            partner = order.partner_id.sudo()
            # The customer entered these values explicitly in this checkout. Keep
            # the order contact current; this is also the source for Meta matching.
            partner.write(partner_vals)
            order.sudo().write({
                "partner_invoice_id": partner.id,
                "partner_shipping_id": partner.id,
            })

        order.sudo().write({
            "meta_first_name": first_name,
            "meta_last_name": last_name,
        })
        request.session["sale_last_order_id"] = order.id
        return {"ok": True, "partner_id": partner.id}

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
