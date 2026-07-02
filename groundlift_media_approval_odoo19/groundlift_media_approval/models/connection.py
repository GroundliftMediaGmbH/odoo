# -*- coding: utf-8 -*-
import ftplib
import io
import os
import posixpath
import socket
import time
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class GlMediaApprovalConnection(models.Model):
    _name = "gl.media.approval.connection"
    _description = "Medienfreigabe Hetzner Verbindung"
    _order = "name"

    name = fields.Char(required=True, default="Hetzner")
    active = fields.Boolean(default=True)
    protocol = fields.Selection(
        [("sftp", "SFTP"), ("ftp", "FTP"), ("ftps", "FTPS")],
        required=True,
        default="sftp",
    )
    host = fields.Char(required=True, help="Servername oder IP-Adresse, z. B. storagebox.example.your-storagebox.de")
    port = fields.Integer(default=22, required=True)
    username = fields.Char(required=True)
    password = fields.Char(required=True, password=True)
    remote_base_path = fields.Char(
        string="Basisordner auf Server",
        required=True,
        default="/",
        help="Alle Unterordner werden darunter angelegt. Beispiel: /mediafreigaben",
    )
    public_base_url = fields.Char(
        string="Öffentliche Vorschau-Basis-URL",
        help="Optional, aber für schnelle Video-Vorschau empfohlen. Beispiel: https://www.example.com/medienfreigabe. "
             "Muss auf denselben Ordner zeigen wie der Basisordner auf dem Server.",
    )
    redirect_preview_to_public = fields.Boolean(
        string="Vorschau direkt über Hetzner laden",
        default=True,
        help="Wenn eine öffentliche Vorschau-Basis-URL gesetzt ist, wird die PIN-geprüfte Vorschau dorthin weitergeleitet. "
             "Der Browser streamt Videos dann direkt vom Webserver statt langsam über Odoo/FTP/SFTP.",
    )
    redirect_download_to_public = fields.Boolean(
        string="Downloads direkt über Hetzner ausliefern",
        default=True,
        help="Wenn eine öffentliche Vorschau-Basis-URL gesetzt ist, leitet Odoo freigegebene Downloads nach der PIN- und Freigabeprüfung direkt zum Hetzner-Webserver weiter. "
             "Der Download läuft dann nicht mehr langsam über Odoo/FTP/SFTP.",
    )
    force_download_via_htaccess = fields.Boolean(
        string="Download per .htaccess erzwingen",
        default=False,
        help="Erst nach erfolgreichem Test aktivieren. Bei URLs mit ?download=1 sendet Hetzner dann Content-Disposition: attachment. "
             "Das ist die zuverlässigste browserübergreifende Methode, damit MP4/MOV-Dateien nicht nur geöffnet, sondern wirklich als Download behandelt werden.",
    )
    force_download_verified = fields.Boolean(
        string="Download-Header getestet",
        default=False,
        readonly=True,
        copy=False,
        help="Wird automatisch gesetzt, wenn der Download-Header-Test wirklich erfolgreich war. Nur dann hängt die Website ?download=1 an die öffentliche Hetzner-URL an.",
    )
    force_download_verified_at = fields.Datetime(
        string="Download-Header getestet am",
        readonly=True,
        copy=False,
    )
    timeout = fields.Integer(default=30, help="Timeout in Sekunden")
    ftp_passive = fields.Boolean(string="FTP Passivmodus", default=True)
    sftp_allow_unknown_host = fields.Boolean(
        string="SFTP unbekannte Hosts erlauben",
        default=True,
        help="Für Odoo.sh meist praktisch. Für maximale Sicherheit deaktivieren und Known Hosts serverseitig pflegen.",
    )
    note = fields.Text()

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Der Verbindungsname muss eindeutig sein."),
    ]

    @api.onchange("protocol")
    def _onchange_protocol(self):
        for rec in self:
            if rec.protocol == "sftp" and (not rec.port or rec.port in (21, 990)):
                rec.port = 22
            elif rec.protocol == "ftp" and (not rec.port or rec.port in (22, 990)):
                rec.port = 21
            elif rec.protocol == "ftps" and (not rec.port or rec.port in (21, 22)):
                rec.port = 990

    @api.constrains("remote_base_path")
    def _check_remote_base_path(self):
        for rec in self:
            if not rec.remote_base_path.startswith("/"):
                raise ValidationError(_("Der Basisordner muss mit / beginnen."))

    def action_test_connection(self):
        self.ensure_one()
        with self._client() as client:
            client.ensure_dir(self.remote_base_path)
            client.list_dir(self.remote_base_path)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Verbindung erfolgreich"),
                "message": _("Der Basisordner ist erreichbar."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_test_public_preview_url(self):
        """Verify that remote_base_path and public_base_url really point to the same directory."""
        self.ensure_one()
        if not self.public_base_url:
            raise UserError(_("Bitte zuerst die öffentliche Vorschau-Basis-URL eintragen."))

        stamp = str(int(time.time()))
        filename = "odoo_public_preview_test_%s.txt" % stamp
        marker = ("groundlift-medienfreigabe-public-test-%s" % stamp).encode("utf-8")
        remote_path = self.build_remote_path(filename)
        public_url = self.get_public_url(remote_path)
        timeout = max(5, min(int(self.timeout or 30), 60))

        try:
            with self._client() as client:
                client.upload_bytes(remote_path, marker)
            req = Request(public_url, headers={"User-Agent": "Odoo Groundlift Medienfreigabe"})
            try:
                with urlopen(req, timeout=timeout) as response:
                    body = response.read(len(marker) + 256)
                    status = getattr(response, "status", 200)
            except HTTPError as exc:
                raise UserError(_(
                    "Die Datei wurde per FTP/SFTP geschrieben, ist unter der öffentlichen URL aber nicht erreichbar.\n"
                    "HTTP-Status: %(status)s\nURL: %(url)s\n\n"
                    "Bitte prüfen: Der Basisordner auf Server muss exakt zum öffentlichen Webordner der Domain passen."
                ) % {"status": exc.code, "url": public_url}) from exc
            except URLError as exc:
                raise UserError(_(
                    "Die öffentliche URL konnte von Odoo aus nicht geladen werden.\nURL: %(url)s\nFehler: %(error)s"
                ) % {"url": public_url, "error": exc}) from exc

            if status != 200 or marker not in body:
                raise UserError(_(
                    "Die öffentliche Vorschau-URL zeigt nicht auf dieselbe Datei wie der FTP/SFTP-Basisordner.\n"
                    "URL: %(url)s\n\n"
                    "Bitte Basisordner und öffentliche Vorschau-Basis-URL korrigieren. Häufig ist /public_html nur relativ zum Login, "
                    "oder die Domain zeigt auf einen anderen Document-Root."
                ) % {"url": public_url})

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Öffentliche Vorschau funktioniert"),
                    "message": _("Odoo konnte eine Testdatei schreiben und über die öffentliche URL wieder laden."),
                    "type": "success",
                    "sticky": False,
                },
            }
        finally:
            try:
                with self._client() as client:
                    client.delete_file(remote_path)
            except Exception:
                pass

    def action_install_download_htaccess(self):
        """Install/update the .htaccess block that forces true file downloads.

        Static files delivered directly by Hetzner cannot receive Odoo response
        headers. Therefore the public webserver has to send
        Content-Disposition: attachment for download URLs. This method only
        manages the marked Groundlift block and preserves any existing custom
        .htaccess content outside the markers.
        """
        self.ensure_one()
        if not self.public_base_url:
            raise UserError(_("Bitte zuerst die öffentliche Vorschau-Basis-URL eintragen."))

        htaccess_path = self.build_remote_path(".htaccess")
        stamp = str(int(time.time()))
        test_filename = "odoo_download_header_test_%s.txt" % stamp
        test_marker = ("groundlift-download-header-test-%s" % stamp).encode("utf-8")
        test_path = self.build_remote_path(test_filename)
        test_url = self.get_public_url(test_path) + "?download=1"
        timeout = max(5, min(int(self.timeout or 30), 60))

        begin = "# BEGIN Groundlift Medienfreigabe Download"
        end = "# END Groundlift Medienfreigabe Download"
        block = """# BEGIN Groundlift Medienfreigabe Download
# Erzwingt echte Datei-Downloads für öffentliche Medien-URLs, wenn Odoo
# nach erfolgreicher Freigabeprüfung auf die Hetzner-Datei mit ?download=1 weiterleitet.
<IfModule mod_setenvif.c>
    SetEnvIfNoCase THE_REQUEST "[?&]download=1([&\\s]|$)" glma_force_download=1
    SetEnvIfNoCase Request_URI "[?&]download=1(&|$)" glma_force_download=1
</IfModule>
<IfModule mod_headers.c>
    Header set Content-Disposition "attachment" env=glma_force_download
    Header set X-Content-Type-Options "nosniff" env=glma_force_download
</IfModule>
# END Groundlift Medienfreigabe Download
"""

        try:
            with self._client() as client:
                existing = b""
                try:
                    existing = client.read_bytes(htaccess_path)
                except Exception:
                    existing = b""

                text = existing.decode("utf-8", errors="replace") if existing else ""
                if begin in text and end in text:
                    before, rest = text.split(begin, 1)
                    _old_block, after = rest.split(end, 1)
                    text = before.rstrip() + "\n\n" + block.rstrip() + "\n" + after.lstrip("\r\n")
                else:
                    if text and not text.endswith("\n"):
                        text += "\n"
                    if text:
                        text += "\n"
                    text += block

                client.upload_bytes(htaccess_path, text.encode("utf-8"))
                client.upload_bytes(test_path, test_marker)

            req = Request(test_url, headers={"User-Agent": "Odoo Groundlift Medienfreigabe"})
            try:
                with urlopen(req, timeout=timeout) as response:
                    body = response.read(len(test_marker) + 256)
                    status = getattr(response, "status", 200)
                    content_disposition = response.headers.get("Content-Disposition", "")
            except HTTPError as exc:
                raise UserError(_(
                    "Die .htaccess wurde geschrieben, aber der öffentliche Testaufruf ist fehlgeschlagen.\n"
                    "HTTP-Status: %(status)s\nURL: %(url)s\n\n"
                    "Wenn Status 500 erscheint, erlaubt der Hetzner-Webserver vermutlich eine der .htaccess-Direktiven nicht. "
                    "Dann bitte die .htaccess im Medienordner prüfen oder die Regel über den Webserver konfigurieren."
                ) % {"status": exc.code, "url": test_url}) from exc
            except URLError as exc:
                raise UserError(_(
                    "Die .htaccess wurde geschrieben, aber die öffentliche Testdatei konnte von Odoo aus nicht geladen werden.\n"
                    "URL: %(url)s\nFehler: %(error)s"
                ) % {"url": test_url, "error": exc}) from exc

            if status != 200 or test_marker not in body:
                raise UserError(_(
                    "Die öffentliche URL zeigt nicht auf die Testdatei aus dem FTP/SFTP-Basisordner.\n"
                    "URL: %(url)s\n\n"
                    "Bitte zuerst den Button „Öffentliche URL testen“ erfolgreich ausführen."
                ) % {"url": test_url})

            if "attachment" not in (content_disposition or "").lower():
                raise UserError(_(
                    "Die Testdatei ist erreichbar, aber Hetzner sendet noch keinen Download-Header.\n"
                    "Erwartet: Content-Disposition: attachment\n"
                    "Tatsächlich: %(header)s\n\n"
                    "Bitte prüfen, ob Apache .htaccess und mod_headers für diesen Webspace aktiv sind."
                ) % {"header": content_disposition or _("kein Header")})

            self.write({
                "force_download_via_htaccess": True,
                "force_download_verified": True,
                "force_download_verified_at": fields.Datetime.now(),
            })
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Download-Header aktiv"),
                    "message": _("Hetzner sendet für ?download=1 jetzt Content-Disposition: attachment. Downloads werden damit serverseitig erzwungen."),
                    "type": "success",
                    "sticky": False,
                },
            }
        finally:
            try:
                with self._client() as client:
                    client.delete_file(test_path)
            except Exception:
                pass

    def build_remote_path(self, *parts):
        self.ensure_one()
        base = self._clean_remote_path(self.remote_base_path)
        cleaned = [self._sanitize_path_part(p) for p in parts if p]
        path = posixpath.join(base, *cleaned) if cleaned else base
        return self._clean_remote_path(path)

    def get_public_url(self, remote_path):
        """Return a browser URL for a file stored below remote_base_path.

        This is intentionally optional. If public_base_url is empty, Odoo keeps
        serving the file through the protected proxy route. If it is set, the
        preview route can authenticate the PIN session and then redirect the
        browser to the webserver URL so video range requests are handled by
        Hetzner/Apache/Nginx instead of by Odoo over FTP/SFTP.
        """
        self.ensure_one()
        if not self.public_base_url:
            return False
        remote_path = self._clean_remote_path(remote_path)
        base = self._clean_remote_path(self.remote_base_path)
        rel = remote_path
        if remote_path == base:
            rel = ""
        elif remote_path.startswith(base.rstrip("/") + "/"):
            rel = remote_path[len(base.rstrip("/")) + 1:]
        else:
            rel = posixpath.basename(remote_path)
        encoded = "/".join(quote(part) for part in rel.split("/") if part)
        base_url = (self.public_base_url or "").rstrip("/")
        return base_url + (("/" + encoded) if encoded else "")

    @staticmethod
    def _clean_remote_path(path):
        path = (path or "/").replace("\\", "/")
        path = posixpath.normpath(path)
        if not path.startswith("/"):
            path = "/" + path
        return path

    @staticmethod
    def _sanitize_path_part(value):
        value = (value or "").strip().replace("\\", "-").replace("/", "-")
        value = value.replace("..", "-")
        value = "".join(ch for ch in value if ch.isalnum() or ch in " ._-()[]äöüÄÖÜß")
        value = value.strip(" .")
        return value or "ordner"

    @contextmanager
    def _client(self):
        self.ensure_one()
        client = None
        try:
            if self.protocol == "sftp":
                client = _SFTPClientWrapper(self)
            else:
                client = _FTPClientWrapper(self)
            client.connect()
            yield client
        finally:
            if client:
                client.close()


class _SFTPClientWrapper:
    def __init__(self, connection):
        self.connection = connection
        self.transport = None
        self.sftp = None

    def connect(self):
        try:
            import paramiko
        except Exception as exc:  # pragma: no cover - depends on server env
            raise UserError(_("Für SFTP muss auf Odoo.sh das Python-Paket 'paramiko' installiert sein. Eine requirements.txt liegt im ZIP.")) from exc
        try:
            sock = socket.create_connection((self.connection.host, int(self.connection.port)), timeout=self.connection.timeout)
            self.transport = paramiko.Transport(sock)
            self.transport.connect(username=self.connection.username, password=self.connection.password)
            self.sftp = paramiko.SFTPClient.from_transport(self.transport)
        except Exception as exc:
            raise UserError(_("SFTP-Verbindung fehlgeschlagen: %s") % exc) from exc

    def close(self):
        try:
            if self.sftp:
                self.sftp.close()
        finally:
            if self.transport:
                self.transport.close()

    def ensure_dir(self, path):
        path = GlMediaApprovalConnection._clean_remote_path(path)
        current = "/"
        for part in [p for p in path.split("/") if p]:
            current = posixpath.join(current, part)
            try:
                self.sftp.stat(current)
            except IOError:
                try:
                    self.sftp.mkdir(current)
                except Exception as exc:
                    raise UserError(_("Der Remote-Ordner konnte nicht angelegt werden: %s\nPfad: %s\nBitte Basisordner und Schreibrechte des Hetzner-Benutzers prüfen.") % (exc, current)) from exc

    def list_dir(self, path):
        return self.sftp.listdir(path)

    def upload_bytes(self, remote_path, content):
        folder = posixpath.dirname(remote_path)
        self.ensure_dir(folder)
        try:
            with self.sftp.open(remote_path, "wb") as remote_file:
                remote_file.write(content)
        except Exception as exc:
            raise UserError(_("Der Hetzner-Server verweigert den Schreibzugriff auf die Datei.\nPfad: %s\nFehler: %s") % (remote_path, exc)) from exc

    def upload_fileobj(self, remote_path, stream):
        folder = posixpath.dirname(remote_path)
        self.ensure_dir(folder)
        try:
            stream.seek(0)
        except Exception:
            pass
        try:
            with self.sftp.open(remote_path, "wb") as remote_file:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    remote_file.write(chunk)
        except Exception as exc:
            raise UserError(_("Der Hetzner-Server verweigert den Schreibzugriff auf die Datei.\nPfad: %s\nFehler: %s") % (remote_path, exc)) from exc

    def write_chunk(self, remote_path, content, append=False, offset=None):
        folder = posixpath.dirname(remote_path)
        self.ensure_dir(folder)
        try:
            if offset is not None:
                offset = int(offset or 0)
                if offset <= 0:
                    mode = "wb"
                    with self.sftp.open(remote_path, mode) as remote_file:
                        remote_file.write(content or b"")
                else:
                    # Nicht alle SFTP-Server erlauben den Append-Modus.
                    # Darum schreiben wir ab dem konkreten Byte-Offset.
                    with self.sftp.open(remote_path, "r+b") as remote_file:
                        remote_file.seek(offset)
                        remote_file.write(content or b"")
            else:
                mode = "ab" if append else "wb"
                with self.sftp.open(remote_path, mode) as remote_file:
                    remote_file.write(content or b"")
        except Exception as exc:
            raise UserError(_("Der Hetzner-Server verweigert den Schreibzugriff auf die Datei.\nPfad: %s\nFehler: %s\nHinweis: Bitte prüfen, ob der Basisordner wirklich beschreibbar ist. Bei Hetzner-Webhosting liegt public_html häufig relativ zum FTP/SFTP-Login.") % (remote_path, exc)) from exc

    def read_bytes(self, remote_path, offset=0, length=None):
        with self.sftp.open(remote_path, "rb") as remote_file:
            if offset:
                remote_file.seek(offset)
            return remote_file.read(length) if length else remote_file.read()

    def delete_file(self, remote_path):
        try:
            self.sftp.remove(remote_path)
        except IOError:
            return False
        return True


class _FTPClientWrapper:
    class _StopRead(Exception):
        pass

    def __init__(self, connection):
        self.connection = connection
        self.ftp = None

    def connect(self):
        try:
            if self.connection.protocol == "ftps":
                self.ftp = ftplib.FTP_TLS(timeout=self.connection.timeout)
            else:
                self.ftp = ftplib.FTP(timeout=self.connection.timeout)
            self.ftp.connect(self.connection.host, int(self.connection.port), timeout=self.connection.timeout)
            self.ftp.login(self.connection.username, self.connection.password)
            if self.connection.protocol == "ftps":
                self.ftp.prot_p()
            self.ftp.set_pasv(bool(self.connection.ftp_passive))
        except Exception as exc:
            raise UserError(_("FTP/FTPS-Verbindung fehlgeschlagen: %s") % exc) from exc

    def close(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception:
                self.ftp.close()

    def ensure_dir(self, path):
        path = GlMediaApprovalConnection._clean_remote_path(path)
        try:
            self.ftp.cwd("/")
            for part in [p for p in path.split("/") if p]:
                try:
                    self.ftp.cwd(part)
                except ftplib.error_perm:
                    self.ftp.mkd(part)
                    self.ftp.cwd(part)
        except Exception as exc:
            raise UserError(_("Der Remote-Ordner konnte nicht angelegt/geöffnet werden: %s\nPfad: %s\nBitte Basisordner und Schreibrechte des Hetzner-Benutzers prüfen.") % (exc, path)) from exc

    def list_dir(self, path):
        current = self.ftp.pwd()
        try:
            self.ftp.cwd(path)
            return self.ftp.nlst()
        finally:
            self.ftp.cwd(current)

    def upload_bytes(self, remote_path, content):
        folder = posixpath.dirname(remote_path)
        self.ensure_dir(folder)
        try:
            with io.BytesIO(content) as stream:
                self.ftp.storbinary("STOR " + remote_path, stream)
        except Exception as exc:
            raise UserError(_("Der Hetzner-Server verweigert den Schreibzugriff auf die Datei.\nPfad: %s\nFehler: %s") % (remote_path, exc)) from exc

    def upload_fileobj(self, remote_path, stream):
        folder = posixpath.dirname(remote_path)
        self.ensure_dir(folder)
        try:
            stream.seek(0)
        except Exception:
            pass
        try:
            self.ftp.storbinary("STOR " + remote_path, stream, blocksize=1024 * 1024)
        except Exception as exc:
            raise UserError(_("Der Hetzner-Server verweigert den Schreibzugriff auf die Datei.\nPfad: %s\nFehler: %s") % (remote_path, exc)) from exc

    def write_chunk(self, remote_path, content, append=False, offset=None):
        folder = posixpath.dirname(remote_path)
        self.ensure_dir(folder)
        try:
            with io.BytesIO(content or b"") as stream:
                if offset is not None:
                    offset = int(offset or 0)
                    if offset <= 0:
                        self.ftp.storbinary("STOR " + remote_path, stream, blocksize=1024 * 1024)
                    else:
                        # REST + STOR ist stabiler als APPE, weil einige Server Append verbieten.
                        self.ftp.storbinary("STOR " + remote_path, stream, blocksize=1024 * 1024, rest=str(offset))
                else:
                    command = "APPE " if append else "STOR "
                    self.ftp.storbinary(command + remote_path, stream, blocksize=1024 * 1024)
        except Exception as exc:
            raise UserError(_("Der Hetzner-Server verweigert den Schreibzugriff auf die Datei.\nPfad: %s\nFehler: %s\nHinweis: Bitte prüfen, ob der Basisordner wirklich beschreibbar ist. Bei Hetzner-Webhosting liegt public_html häufig relativ zum FTP/SFTP-Login.") % (remote_path, exc)) from exc

    def read_bytes(self, remote_path, offset=0, length=None):
        chunks = []
        collected = 0

        def callback(data):
            nonlocal collected
            if length is not None:
                remaining = length - collected
                if remaining <= 0:
                    raise self._StopRead()
                data = data[:remaining]
            chunks.append(data)
            collected += len(data)
            if length is not None and collected >= length:
                raise self._StopRead()

        try:
            if offset:
                self.ftp.retrbinary("RETR " + remote_path, callback, rest=offset)
            else:
                self.ftp.retrbinary("RETR " + remote_path, callback)
        except self._StopRead:
            pass
        return b"".join(chunks)

    def delete_file(self, remote_path):
        try:
            self.ftp.delete(remote_path)
        except ftplib.all_errors:
            return False
        return True
