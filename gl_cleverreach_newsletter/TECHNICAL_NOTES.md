# Technische Hinweise

## Datenmodelle

- `gl.cleverreach.newsletter.config`: globale Konfiguration und API-Zugang.
- `gl.cleverreach.group`: importierte CleverReach-Gruppen/Empfängerlisten.
- `gl.cleverreach.newsletter.template`: austauschbare HTML-Vorlagen.
- `gl.cleverreach.event.queue`: Events, die in „Angekündigt“ verschoben wurden.
- `gl.cleverreach.newsletter.job`: erzeugte Newsletter-Aufträge.

## Cronjobs

- `Groundlift CleverReach: neue angekündigte Events prüfen`: alle 15 Minuten, läuft erst ab lokaler Erstellungsstunde.
- `Groundlift CleverReach: 14-tägigen Eventnewsletter prüfen`: alle 15 Minuten, läuft erst ab lokaler Erstellungsstunde.
- `Groundlift CleverReach: Newsletter-Watchdog`: stündlich.
- `Groundlift CleverReach: fällige Newsletter versenden`: alle 5 Minuten, verschickt in Odoo fällige Newsletter per CleverReach-Sofortversand.

## Erweiterungspunkte

Die wichtigste Stelle für CleverReach-Payload-Anpassungen ist:

```python
CleverReachNewsletterJob._cleverreach_create_mailing()
CleverReachNewsletterJob._cleverreach_send_mailing_now()
```

CleverReach wird nicht mehr für zukünftige Terminierung genutzt. Falls CleverReach für euren Account einen anderen Endpoint für Sofortversand erwartet, muss nur dort die Payload bzw. der Endpoint ergänzt werden.


## Version 19.0.1.2.0 – OAuth-Fix für CleverReach Release

Der Fehler `Forbidden: invalid scope` bei `POST /mailings/{id}/release` ist kein Payload-Fehler, sondern ein Token-/Scope-Fehler. Diese Version ergänzt deshalb:

- Authorization Code Flow über `/gl_cleverreach/oauth/callback`
- Speicherung von `oauth_refresh_token` und `oauth_scope`
- automatische Token-Erneuerung über `grant_type=refresh_token`
- weiterhin Fallback auf Client Credentials, solange kein Refresh Token vorhanden ist
- klarere Fehlermeldung, wenn auch der Benutzer-OAuth-Token keinen Release-/Mailings-Scope besitzt

Relevante Methoden:

```python
CleverReachNewsletterConfig.action_open_oauth_authorization()
CleverReachNewsletterConfig._exchange_authorization_code()
CleverReachNewsletterConfig._refresh_access_token_from_refresh_token()
CleverReachNewsletterJob._cleverreach_send_mailing_now()
```


## Version 19.0.1.2.1 – `time`-Integer-Fix für CleverReach Release

CleverReach meldete bei `POST /mailings/{id}/release`:

```text
Invalid value specified for `time`. Expecting integer value
```

Die Methode `CleverReachNewsletterJob._cleverreach_send_mailing_now()` sendet deshalb nun zuerst einen Release-Payload mit einem Integer-Unix-Timestamp in UTC-Sekunden:

```json
{"time": 1760000000}
```

Als Fallback bleiben ein um 60 Sekunden nach vorne gesetzter Timestamp, Query-Parameter-Varianten sowie die bisherigen leeren Varianten erhalten.


## Version 19.0.1.2.2 – Website-Header-Bild und Kontrast-Fix

- `gl.cleverreach.newsletter.config.image_field_name` nutzt nun standardmäßig `x_studio_website_header`.
- `CleverReachNewsletterConfig._event_image_field()` bevorzugt `x_studio_website_header` auch dann, wenn bestehende Konfigurationsdatensätze noch den alten Wert `image_1920` enthalten.
- `CleverReachNewsletterConfig._normalize_newsletter_html()` entfernt den sichtbaren `<br>`-Fehler in der Ticket-Zeile und setzt kritische dunkle Newsletter-Bereiche auf weiße Schrift.
