# -*- coding: utf-8 -*-
import ftplib
import io
import os
import posixpath
import socket
from contextlib import contextmanager

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

    def build_remote_path(self, *parts):
        self.ensure_one()
        base = self._clean_remote_path(self.remote_base_path)
        cleaned = [self._sanitize_path_part(p) for p in parts if p]
        path = posixpath.join(base, *cleaned) if cleaned else base
        return self._clean_remote_path(path)

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
