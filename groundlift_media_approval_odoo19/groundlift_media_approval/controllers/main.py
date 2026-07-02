# -*- coding: utf-8 -*-
import re

from odoo import http, _
from odoo.http import request, Response
from werkzeug.exceptions import NotFound, Forbidden


class GlMediaApprovalWebsite(http.Controller):
    def _current_person(self):
        person_id = request.session.get("glma_person_id")
        if not person_id:
            return request.env["gl.media.approval.person"].sudo().browse()
        person = request.env["gl.media.approval.person"].sudo().browse(int(person_id))
        if not person.exists() or not person.active:
            request.session.pop("glma_person_id", None)
            return request.env["gl.media.approval.person"].sudo().browse()
        return person

    def _require_person(self):
        person = self._current_person()
        if not person:
            raise Forbidden()
        return person

    @http.route(["/medienfreigabe", "/media-approval"], type="http", auth="public", website=True, sitemap=False)
    def home(self, **kw):
        person = self._current_person()
        error = kw.get("error")
        if not person:
            return request.render("groundlift_media_approval.login", {"error": error})
        folders = request.env["gl.media.approval.folder"].sudo().search([
            ("active", "=", True),
            ("website_visible", "=", True),
        ])
        return request.render("groundlift_media_approval.folder_list", {
            "person": person,
            "folders": folders,
        })

    @http.route("/media-approval/login", type="http", auth="public", website=True, methods=["POST"], sitemap=False)
    def login(self, pin=None, **post):
        person = request.env["gl.media.approval.person"].sudo().authenticate_pin(pin)
        if person:
            request.session["glma_person_id"] = person.id
            return request.redirect("/media-approval")
        return request.redirect("/media-approval?error=1")

    @http.route("/media-approval/logout", type="http", auth="public", website=True, sitemap=False)
    def logout(self, **kw):
        request.session.pop("glma_person_id", None)
        return request.redirect("/media-approval")

    @http.route("/media-approval/folder/<int:folder_id>", type="http", auth="public", website=True, sitemap=False)
    def folder(self, folder_id, file_id=None, **kw):
        person = self._require_person()
        folder = request.env["gl.media.approval.folder"].sudo().browse(folder_id)
        if not folder.exists() or not folder.active or not folder.website_visible:
            raise NotFound()
        domain = [("folder_id", "=", folder.id), ("active", "=", True), ("deleted_remote", "=", False)]
        files = request.env["gl.media.approval.file"].sudo().search(domain)
        selected = request.env["gl.media.approval.file"].sudo().browse()
        if file_id:
            selected = request.env["gl.media.approval.file"].sudo().browse(int(file_id))
            if not selected.exists() or selected.folder_id.id != folder.id or not selected.active:
                selected = request.env["gl.media.approval.file"].sudo().browse()
        if not selected and files:
            selected = files[0]
        return request.render("groundlift_media_approval.folder_detail", {
            "person": person,
            "folder": folder,
            "files": files,
            "selected": selected,
        })

    @http.route("/media-approval/vote/<int:file_id>", type="http", auth="public", website=True, methods=["POST"], sitemap=False)
    def vote(self, file_id, decision=None, **post):
        person = self._require_person()
        media = request.env["gl.media.approval.file"].sudo().browse(file_id)
        if not media.exists() or not media.active or media.deleted_remote:
            raise NotFound()
        media.vote_from_website(person, decision)
        return request.redirect(f"/media-approval/folder/{media.folder_id.id}?file_id={media.id}")

    @http.route("/media-approval/preview/<int:file_id>", type="http", auth="public", website=True, sitemap=False, csrf=False)
    def preview(self, file_id, **kw):
        person = self._require_person()
        media = request.env["gl.media.approval.file"].sudo().browse(file_id)
        if not media.exists() or not media.active or media.deleted_remote:
            raise NotFound()
        # Preview is visible to logged-in PIN persons. The person's own vote is handled separately.
        return self._serve_media(media, inline=True, allow_locked=True)

    @http.route("/media-approval/download/<int:file_id>", type="http", auth="public", website=True, sitemap=False, csrf=False)
    def download(self, file_id, **kw):
        self._require_person()
        media = request.env["gl.media.approval.file"].sudo().browse(file_id)
        if not media.exists() or not media.active or media.deleted_remote:
            raise NotFound()
        if media.decision_state != "approved":
            raise Forbidden()
        return self._serve_media(media, inline=False, allow_locked=False)

    def _serve_media(self, media, inline=True, allow_locked=True):
        size = int(media.size_bytes or 0)
        range_header = request.httprequest.headers.get("Range")
        status = 200
        offset = 0
        length = None
        headers = [
            ("Content-Type", media.mimetype or "application/octet-stream"),
            ("Accept-Ranges", "bytes"),
            ("Cache-Control", "private, max-age=600"),
        ]
        disposition = "inline" if inline else "attachment"
        safe_name = (media.name or "datei").replace('"', "")
        headers.append(("Content-Disposition", f'{disposition}; filename="{safe_name}"'))

        if range_header and size:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
                end = min(end, size - 1)
                if start <= end:
                    offset = start
                    length = end - start + 1
                    status = 206
                    headers.append(("Content-Range", f"bytes {start}-{end}/{size}"))
                    headers.append(("Content-Length", str(length)))
        content = media.read_remote_bytes(offset=offset, length=length)
        if not any(h[0].lower() == "content-length" for h in headers):
            headers.append(("Content-Length", str(len(content))))
        return Response(content, status=status, headers=headers)
