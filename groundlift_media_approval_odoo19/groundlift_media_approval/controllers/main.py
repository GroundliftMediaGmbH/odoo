# -*- coding: utf-8 -*-
import json
import re

from odoo import http, _
from odoo.http import request, Response
from werkzeug.exceptions import NotFound, Forbidden, BadRequest


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
        all_folders = request.env["gl.media.approval.folder"].sudo().search([
            ("active", "=", True),
            ("website_visible", "=", True),
        ])
        folders = all_folders.filtered(lambda f: person in f.reviewer_person_ids or any(person in media.approval_person_ids for media in f.file_ids.filtered(lambda m: m.active and not m.deleted_remote)))
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
        has_folder_access = person in folder.reviewer_person_ids or any(person in media.approval_person_ids for media in folder.file_ids.filtered(lambda m: m.active and not m.deleted_remote))
        if not has_folder_access:
            raise Forbidden()
        domain = [("folder_id", "=", folder.id), ("active", "=", True), ("deleted_remote", "=", False), ("approval_person_ids", "in", [person.id])]
        files = request.env["gl.media.approval.file"].sudo().search(domain)
        selected = request.env["gl.media.approval.file"].sudo().browse()
        if file_id:
            selected = request.env["gl.media.approval.file"].sudo().browse(int(file_id))
            if not selected.exists() or selected.folder_id.id != folder.id or not selected.active or person not in selected.approval_person_ids:
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

    @http.route("/media-approval/preview/<int:file_id>", type="http", auth="public", website=True, methods=["GET", "HEAD"], sitemap=False, csrf=False)
    def preview(self, file_id, **kw):
        person = self._require_person()
        media = request.env["gl.media.approval.file"].sudo().browse(file_id)
        if not media.exists() or not media.active or media.deleted_remote:
            raise NotFound()
        if person not in media.approval_person_ids:
            raise Forbidden()
        return self._serve_media(media, inline=True, allow_locked=True)

    @http.route("/media-approval/download/<int:file_id>", type="http", auth="public", website=True, methods=["GET", "HEAD"], sitemap=False, csrf=False)
    def download(self, file_id, **kw):
        person = self._require_person()
        media = request.env["gl.media.approval.file"].sudo().browse(file_id)
        if not media.exists() or not media.active or media.deleted_remote:
            raise NotFound()
        if person not in media.approval_person_ids:
            raise Forbidden()
        if media.decision_state != "approved":
            raise Forbidden()
        return self._serve_media(media, inline=False, allow_locked=False)


    @http.route("/media-approval/backend/upload", type="http", auth="user", website=True, sitemap=False)
    def backend_upload_page(self, folder_id=None, **kw):
        Folder = request.env["gl.media.approval.folder"].sudo()
        folders = Folder.search([("active", "=", True)], order="sequence, name")
        selected_folder = Folder.browse()
        if folder_id:
            selected_folder = Folder.browse(int(folder_id))
            if not selected_folder.exists():
                selected_folder = Folder.browse()
        return request.render("groundlift_media_approval.backend_upload_page", {
            "folders": folders,
            "selected_folder": selected_folder,
            "max_files": 50,
            "max_size_mb": 200,
        })

    @http.route("/media-approval/backend/upload-file", type="http", auth="user", website=False, methods=["POST"], sitemap=False)
    def backend_upload_file(self, folder_id=None, file=None, **post):
        try:
            folder_id = folder_id or post.get("folder_id")
            uploaded_file = file or request.httprequest.files.get("file")
            if not folder_id:
                raise BadRequest("Ordner fehlt.")
            folder = request.env["gl.media.approval.folder"].sudo().browse(int(folder_id))
            if not folder.exists() or not folder.active:
                raise BadRequest("Ordner wurde nicht gefunden.")
            if not uploaded_file:
                raise BadRequest("Datei fehlt.")
            filename = getattr(uploaded_file, "filename", None) or "datei"
            mimetype = getattr(uploaded_file, "mimetype", None) or getattr(uploaded_file, "content_type", None) or "application/octet-stream"
            stream = getattr(uploaded_file, "stream", uploaded_file)
            size = self._stream_size(stream, fallback=getattr(uploaded_file, "content_length", 0) or 0)
            max_size = 200 * 1024 * 1024
            if size and size > max_size:
                raise BadRequest("Die Datei ist größer als 200 MB.")
            media = request.env["gl.media.approval.file"].sudo().create_from_upload_stream(
                folder,
                filename,
                stream,
                mimetype=mimetype,
                size_bytes=size,
            )
            return self._json_response({
                "ok": True,
                "id": media.id,
                "name": media.name,
                "size_bytes": media.size_bytes,
                "state": media.decision_state,
            })
        except Exception as exc:
            return self._json_response({"ok": False, "error": str(exc)}, status=400)


    @http.route("/media-approval/backend/upload-chunk", type="http", auth="user", website=False, methods=["POST"], sitemap=False)
    def backend_upload_chunk(self, **post):
        try:
            folder_id = post.get("folder_id")
            uploaded_chunk = request.httprequest.files.get("chunk")
            filename = post.get("filename") or "datei"
            mimetype = post.get("mimetype") or "application/octet-stream"
            upload_uid = re.sub(r"[^a-zA-Z0-9_.-]", "", post.get("upload_uid") or "")[:80]
            chunk_index = int(post.get("chunk_index") or 0)
            total_chunks = int(post.get("total_chunks") or 1)
            total_size = int(post.get("total_size") or 0)

            if not folder_id:
                raise BadRequest("Ordner fehlt.")
            if not upload_uid:
                raise BadRequest("Upload-ID fehlt.")
            if chunk_index < 0 or total_chunks < 1 or chunk_index >= total_chunks:
                raise BadRequest("Ungültiger Chunk-Index.")
            if not uploaded_chunk:
                raise BadRequest("Datei-Chunk fehlt.")

            max_size = 200 * 1024 * 1024
            max_chunk_size = 8 * 1024 * 1024
            if total_size and total_size > max_size:
                raise BadRequest("Die Datei ist größer als 200 MB.")

            content = uploaded_chunk.read()
            if len(content) > max_chunk_size + 1024:
                raise BadRequest("Ein Upload-Chunk ist zu groß. Bitte die Seite neu laden und erneut versuchen.")

            folder = request.env["gl.media.approval.folder"].sudo().browse(int(folder_id))
            if not folder.exists() or not folder.active:
                raise BadRequest("Ordner wurde nicht gefunden.")

            Media = request.env["gl.media.approval.file"].sudo()
            filename = Media._sanitize_filename(filename)
            ICP = request.env["ir.config_parameter"].sudo()
            upload_key = "glma.chunk.%s.%s" % (request.env.user.id, upload_uid)
            state_raw = ICP.get_param(upload_key)
            state = json.loads(state_raw) if state_raw else None

            if chunk_index == 0:
                # Validiert früh, damit der Upload sofort mit einer verständlichen Meldung stoppt,
                # wenn im Unterordner noch keine bewertenden Personen hinterlegt sind.
                Media._approval_persons_for_folder(folder)
                folder._update_remote_path()
                with folder.connection_id._client() as client:
                    client.ensure_dir(folder.remote_path)
                    remote_path = Media._unique_remote_path(client, folder, filename)
                    client.write_chunk(remote_path, content, offset=0)
                state = {
                    "folder_id": folder.id,
                    "remote_path": remote_path,
                    "filename": filename,
                    "mimetype": mimetype,
                    "total_size": total_size,
                    "total_chunks": total_chunks,
                    "bytes_written": len(content or b""),
                    "next_chunk_index": 1,
                }
            else:
                if not state:
                    raise BadRequest("Upload-Sitzung wurde nicht gefunden. Bitte diese Datei erneut starten.")
                if int(state.get("folder_id")) != folder.id:
                    raise BadRequest("Upload-Sitzung passt nicht zum ausgewählten Ordner.")
                expected = int(state.get("next_chunk_index") or 0)
                if chunk_index != expected:
                    raise BadRequest("Upload-Chunks kamen nicht in der richtigen Reihenfolge an. Bitte erneut hochladen.")
                expected_offset = int(state.get("bytes_written") or 0)
                expected_by_index = chunk_index * max_chunk_size
                # Bei gleich großen Chunks entspricht bytes_written dem Start-Offset des nächsten Blocks.
                # Wir verlassen uns auf bytes_written, damit auch abweichende letzte/kleinere Chunks robust funktionieren.
                with folder.connection_id._client() as client:
                    client.write_chunk(state["remote_path"], content, offset=expected_offset)
                state["bytes_written"] = expected_offset + len(content or b"")
                state["next_chunk_index"] = chunk_index + 1

            if chunk_index + 1 >= total_chunks:
                media = Media.create_from_remote_upload(
                    folder,
                    state.get("filename") or filename,
                    state["remote_path"],
                    mimetype=state.get("mimetype") or mimetype,
                    size_bytes=state.get("total_size") or total_size,
                )
                ICP.search([("key", "=", upload_key)], limit=1).unlink()
                return self._json_response({
                    "ok": True,
                    "final": True,
                    "id": media.id,
                    "name": media.name,
                    "size_bytes": media.size_bytes,
                    "state": media.decision_state,
                })

            ICP.set_param(upload_key, json.dumps(state))
            return self._json_response({
                "ok": True,
                "final": False,
                "chunk_index": chunk_index,
                "next_chunk_index": state.get("next_chunk_index"),
            })
        except Exception as exc:
            return self._json_response({"ok": False, "error": str(exc)}, status=400)

    @staticmethod
    def _stream_size(stream, fallback=0):
        try:
            current = stream.tell()
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(current)
            return int(size or fallback or 0)
        except Exception:
            return int(fallback or 0)

    @staticmethod
    def _json_response(payload, status=200):
        return Response(json.dumps(payload), status=status, content_type="application/json; charset=utf-8")

    def _serve_media(self, media, inline=True, allow_locked=True):
        # Fast path for previews: after the PIN/session check in the calling route,
        # redirect to the public Hetzner URL. The webserver can then handle byte
        # range requests natively, which makes video start almost immediately.
        force_proxy = str(request.params.get("proxy") or "").lower() in ("1", "true", "yes")
        if inline and not force_proxy and media.connection_id.redirect_preview_to_public:
            public_url = media.get_public_preview_url()
            if public_url:
                return request.redirect(public_url, code=302)

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

        # Fallback safety: some browsers/proxies ask for a video without Range.
        # Do not pull the entire 200 MB file through Odoo just to show metadata;
        # answer with the first small segment as partial content.
        if inline and media.preview_media_type == "video" and not range_header and size and size > 2 * 1024 * 1024:
            offset = 0
            length = 2 * 1024 * 1024
            status = 206
            headers.append(("Content-Range", f"bytes 0-{length - 1}/{size}"))
            headers.append(("Content-Length", str(length)))

        if request.httprequest.method == "HEAD":
            if not any(h[0].lower() == "content-length" for h in headers):
                headers.append(("Content-Length", str(size)))
            return Response(b"", status=status, headers=headers)

        content = media.read_remote_bytes(offset=offset, length=length)
        if not any(h[0].lower() == "content-length" for h in headers):
            headers.append(("Content-Length", str(len(content))))
        return Response(content, status=status, headers=headers)
