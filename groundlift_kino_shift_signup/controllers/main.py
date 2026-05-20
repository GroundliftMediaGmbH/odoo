# -*- coding: utf-8 -*-
from urllib.parse import quote

from odoo import http
from odoo.http import request


class GroundliftKinoShiftController(http.Controller):

    def _get_campaign_invite_slot(self, campaign_token=None, employee_token=None, slot_id=None):
        Campaign = request.env["gl.kino.shift.campaign"].sudo()
        Invite = request.env["gl.kino.shift.invite"].sudo()
        Slot = request.env["gl.kino.shift.slot"].sudo()

        campaign = False
        if campaign_token:
            campaign = Campaign.search([("token", "=", campaign_token)], limit=1)

        invite = False
        if campaign and employee_token:
            invite = Invite.search(
                [("campaign_id", "=", campaign.id), ("token", "=", employee_token)],
                limit=1,
            )

        slot = False
        if slot_id:
            try:
                slot = Slot.browse(int(slot_id)).exists()
            except (TypeError, ValueError):
                slot = False

        return campaign, invite, slot

    def _redirect_back(self, campaign, invite=False, message=""):
        campaign_token = campaign.token if campaign else ""
        if invite:
            return request.redirect("/kino-dienstplan/%s/%s?message=%s" % (campaign_token, invite.token, quote(message or "")))
        return request.redirect("/kino-dienstplan/%s?message=%s" % (campaign_token, quote(message or "")))

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

        preference_by_slot_id = {}
        strong_remaining = 0
        priority_quota = 0
        if campaign and invite:
            preference_by_slot_id = campaign.get_preference_by_slot_for_employee(invite.employee_id)
            strong_remaining = campaign.get_strong_priority_remaining(invite.employee_id)
            priority_quota = campaign.priority_quota

        values = {
            "campaign": campaign,
            "invite": invite,
            "message": kwargs.get("message"),
            "week_rows": campaign.get_week_rows() if campaign else [],
            "preference_by_slot_id": preference_by_slot_id,
            "strong_remaining": strong_remaining,
            "priority_quota": priority_quota,
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
    def kino_shift_signup(self, campaign_token=None, employee_token=None, slot_id=None, priority=None, **post):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Eintragung konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message)

        message = campaign.action_signup_from_invite(invite, slot, priority=priority)
        return self._redirect_back(campaign, invite, message)

    @http.route(
        "/kino-dienstplan/swap/request",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def kino_shift_swap_request(self, campaign_token=None, employee_token=None, slot_id=None, **post):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Tauschanfrage konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message)

        message = campaign.action_request_swap_from_invite(invite, slot)
        return self._redirect_back(campaign, invite, message)

    @http.route(
        "/kino-dienstplan/swap/accept",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def kino_shift_swap_accept(self, campaign_token=None, employee_token=None, slot_id=None, **post):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Tauschanfrage konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message)

        message = campaign.action_respond_swap_from_invite(invite, slot, accept=True)
        return self._redirect_back(campaign, invite, message)

    @http.route(
        "/kino-dienstplan/swap/respond/<string:campaign_token>/<string:employee_token>/<int:slot_id>/<string:answer>",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def kino_shift_swap_respond_email(self, campaign_token=None, employee_token=None, slot_id=None, answer=None, **kwargs):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Tauschanfrage konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message)

        accept = answer == "yes"
        message = campaign.action_respond_swap_from_invite(invite, slot, accept=accept)
        return self._redirect_back(campaign, invite, message)
