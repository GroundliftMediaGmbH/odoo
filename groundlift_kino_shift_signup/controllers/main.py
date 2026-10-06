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

    def _page_values(self, campaign=False, invite=False, message=False, employee_portal=False, portal_month_entries=None):
        preference_by_slot_id = {}
        strong_remaining = 0
        priority_quota = 0
        takeover_request_slots = request.env["gl.kino.shift.slot"].sudo()
        correction_available_by_slot_id = {}
        swap_available_by_slot_id = {}
        monthly_shift_count = 0
        monthly_shift_remaining = 0
        max_monthly_shift_count = campaign.max_monthly_shift_count if campaign else 6

        if campaign:
            swap_available_by_slot_id = {
                slot.id: campaign.is_swap_allowed_for_slot(slot)
                for slot in campaign.slot_ids
            }

        if campaign and invite:
            preference_by_slot_id = campaign.get_preference_by_slot_for_employee(invite.employee_id)
            strong_remaining = campaign.get_strong_priority_remaining(invite.employee_id)
            priority_quota = campaign.priority_quota
            monthly_shift_count = campaign.get_employee_shift_count(invite.employee_id)
            monthly_shift_remaining = campaign.get_monthly_shift_remaining(invite.employee_id)
            max_monthly_shift_count = campaign.max_monthly_shift_count
            takeover_request_slots = campaign.slot_ids.filtered(
                lambda slot: slot.employee_id.id == invite.employee_id.id and bool(slot.takeover_requested_by_id)
            ).sorted("date")
            correction_available_by_slot_id = {
                slot.id: campaign.can_correct_assignment_from_invite(invite, slot)
                for slot in campaign.slot_ids
            }

        return {
            "campaign": campaign,
            "invite": invite,
            "message": message,
            "week_rows": campaign.get_week_rows() if campaign else [],
            "preference_by_slot_id": preference_by_slot_id,
            "strong_remaining": strong_remaining,
            "priority_quota": priority_quota,
            "takeover_request_slots": takeover_request_slots,
            "correction_available_by_slot_id": correction_available_by_slot_id,
            "swap_available_by_slot_id": swap_available_by_slot_id,
            "monthly_shift_count": monthly_shift_count,
            "monthly_shift_remaining": monthly_shift_remaining,
            "max_monthly_shift_count": max_monthly_shift_count,
            "employee_portal": employee_portal,
            "portal_month_entries": portal_month_entries or [],
        }

    def _redirect_back(self, campaign, invite=False, message="", return_access_token=False):
        campaign_token = campaign.token if campaign else ""
        if invite and return_access_token:
            Portal = request.env["gl.kino.shift.employee.portal"].sudo()
            portal = Portal.search(
                [("token", "=", return_access_token), ("employee_id", "=", invite.employee_id.id)],
                limit=1,
            )
            if portal:
                return request.redirect(
                    "/kino-dienstplan/mitarbeiter/%s?campaign=%s&message=%s"
                    % (portal.token, campaign_token, quote(message or ""))
                )
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
            campaign = Campaign.search([("state", "in", ["open", "done"])], limit=1)

        invite = False
        if campaign and employee_token:
            invite = Invite.search(
                [("campaign_id", "=", campaign.id), ("token", "=", employee_token)],
                limit=1,
            )

        if campaign and invite:
            portal = request.env["gl.kino.shift.employee.portal"].sudo().get_or_create_for_employee(invite.employee_id)
            target = "/kino-dienstplan/mitarbeiter/%s?campaign=%s" % (portal.token, campaign.token)
            if kwargs.get("message"):
                target += "&message=%s" % quote(kwargs.get("message") or "")
            return request.redirect(target)

        values = self._page_values(
            campaign=campaign,
            invite=invite,
            message=kwargs.get("message"),
        )
        return request.render("groundlift_kino_shift_signup.kino_shift_page", values)

    @http.route(
        "/kino-dienstplan/mitarbeiter/<string:access_token>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def kino_shift_employee_portal(self, access_token=None, campaign=None, **kwargs):
        Portal = request.env["gl.kino.shift.employee.portal"].sudo()
        Invite = request.env["gl.kino.shift.invite"].sudo()

        employee_portal = Portal.search([("token", "=", access_token)], limit=1)
        if not employee_portal:
            return request.not_found()

        invites = Invite.search([("employee_id", "=", employee_portal.employee_id.id)])
        invite_list = list(invites)
        invite_list.sort(
            key=lambda item: (
                item.campaign_id.request_sent_date or item.campaign_id.target_month,
                item.campaign_id.target_month,
                item.campaign_id.id,
            ),
            reverse=True,
        )

        selected_invite = False
        if campaign:
            selected_invite = next(
                (item for item in invite_list if item.campaign_id.token == campaign),
                False,
            )
        if not selected_invite and invite_list:
            selected_invite = invite_list[0]

        base_path = "/kino-dienstplan/mitarbeiter/%s" % employee_portal.token
        month_entries = [
            {
                "campaign": item.campaign_id,
                "invite": item,
                "url": "%s?campaign=%s" % (base_path, item.campaign_id.token),
                "active": bool(selected_invite and item.id == selected_invite.id),
            }
            for item in sorted(invite_list, key=lambda item: (item.campaign_id.target_month, item.campaign_id.id), reverse=True)
        ]

        selected_campaign = selected_invite.campaign_id if selected_invite else False
        values = self._page_values(
            campaign=selected_campaign,
            invite=selected_invite,
            message=kwargs.get("message"),
            employee_portal=employee_portal,
            portal_month_entries=month_entries,
        )
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
    def kino_shift_signup(self, campaign_token=None, employee_token=None, slot_id=None, priority=None, return_access_token=None, **post):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Eintragung konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

        message = campaign.action_signup_from_invite(invite, slot, priority=priority)
        return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

    @http.route(
        "/kino-dienstplan/correct",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def kino_shift_correct(self, campaign_token=None, employee_token=None, slot_id=None, return_access_token=None, **post):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Korrektur konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

        message = campaign.action_correct_assignment_from_invite(invite, slot)
        return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

    @http.route(
        "/kino-dienstplan/swap/request",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def kino_shift_swap_request(self, campaign_token=None, employee_token=None, slot_id=None, return_access_token=None, **post):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Tauschanfrage konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

        message = campaign.action_request_swap_from_invite(invite, slot)
        return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

    @http.route(
        "/kino-dienstplan/swap/accept",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def kino_shift_swap_accept(self, campaign_token=None, employee_token=None, slot_id=None, return_access_token=None, **post):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Tauschanfrage konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

        message = campaign.action_respond_swap_from_invite(invite, slot, accept=True)
        return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

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

    @http.route(
        "/kino-dienstplan/fill/respond/<string:campaign_token>/<string:employee_token>/<int:slot_id>/<string:answer>",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def kino_shift_fill_respond_email(self, campaign_token=None, employee_token=None, slot_id=None, answer=None, **kwargs):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Zusatztermin-Anfrage konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message)

        accept = answer == "yes"
        message = campaign.action_respond_fill_request_from_invite(invite, slot, accept=accept)
        return self._redirect_back(campaign, invite, message)

    @http.route(
        "/kino-dienstplan/takeover/respond",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def kino_shift_takeover_respond_page(self, campaign_token=None, employee_token=None, slot_id=None, answer=None, return_access_token=None, **post):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Übergabeanfrage konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

        accept = answer == "yes"
        message = campaign.action_respond_takeover_from_owner(invite, slot, accept=accept)
        return self._redirect_back(campaign, invite, message, return_access_token=return_access_token)

    @http.route(
        "/kino-dienstplan/takeover/respond/<string:campaign_token>/<string:employee_token>/<int:slot_id>/<string:answer>",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def kino_shift_takeover_respond_email(self, campaign_token=None, employee_token=None, slot_id=None, answer=None, **kwargs):
        campaign, invite, slot = self._get_campaign_invite_slot(campaign_token, employee_token, slot_id)

        if not campaign or not invite or not slot:
            message = "Die Übergabeanfrage konnte nicht verarbeitet werden. Bitte öffne den Link aus deiner E-Mail erneut."
            return self._redirect_back(campaign, invite, message)

        accept = answer == "yes"
        message = campaign.action_respond_takeover_from_owner(invite, slot, accept=accept)
        return self._redirect_back(campaign, invite, message)
