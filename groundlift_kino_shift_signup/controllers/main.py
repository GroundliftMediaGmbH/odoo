# -*- coding: utf-8 -*-
from urllib.parse import quote

from odoo import http
from odoo.http import request


class GroundliftKinoShiftController(http.Controller):

    @http.route(
        [
            "/kino-dienstplan",
            "/kino-dienstplan/<string:campaign_token>",
            "/kino-dienstplan/<string:campaign_token>/<string:employee_token>",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def kino_shift_page(self, campaign_token=None, employee_token=None, **kwargs):
        Campaign = request.env["gl.kino.shift.campaign"].sudo()
        Invite = request.env["gl.kino.shift.invite"].sudo()

        campaign = False
        if campaign_token:
            campaign = Campaign.search([("token", "=", campaign_token)], limit=1)
        if not campaign:
            campaign = Campaign.search([("state", "in", ["open", "done"])] , limit=1)

        invite = False
        if campaign and employee_token:
            invite = Invite.search(
                [("campaign_id", "=", campaign.id), ("token", "=", employee_token)],
                limit=1,
            )

        values = {
            "campaign": campaign,
            "invite": invite,
            "message": kwargs.get("message"),
            "week_rows": campaign.get_week_rows() if campaign else [],
        }
        return request.render("groundlift_kino_shift_signup.kino_shift_page", values)

    @http.route(
        "/kino-dienstplan/signup",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def kino_shift_signup(self, campaign_token=None, employee_token=None, slot_id=None, **post):
        Campaign = request.env["gl.kino.shift.campaign"].sudo()
        Invite = request.env["gl.kino.shift.invite"].sudo()
        Slot = request.env["gl.kino.shift.slot"].sudo()

        campaign = Campaign.search([("token", "=", campaign_token)], limit=1)
        invite = False
        slot = False
        if campaign and employee_token:
            invite = Invite.search(
                [("campaign_id", "=", campaign.id), ("token", "=", employee_token)],
                limit=1,
            )
        if slot_id:
            try:
                slot = Slot.browse(int(slot_id)).exists()
            except (TypeError, ValueError):
                slot = False

        if not campaign or not invite or not slot:
            message = "Die Eintragung konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            redirect_token = campaign.token if campaign else ""
            return request.redirect("/kino-dienstplan/%s?message=%s" % (redirect_token, quote(message)))

        message = campaign.action_signup_from_invite(invite, slot)
        return request.redirect(
            "/kino-dienstplan/%s/%s?message=%s" % (campaign.token, invite.token, quote(message))
        )
