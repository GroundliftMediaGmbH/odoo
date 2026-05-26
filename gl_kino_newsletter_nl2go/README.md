# GROUNDLIFT Kino Newsletter Newsletter2Go

Odoo-19-SH-Modul für den Kino-Stegen-Wochennewsletter und die sachliche Presse-Mail.

## Funktionen

- Lädt montags um 17:00 Uhr lokaler Zeit das Wochenprogramm aus der Cinetixx-API.
- Erzeugt eine Odoo-Vorschau für den Kinonewsletter auf Basis von `newsletter_template.html`.
- Fügt pro Vorstellung einen Button **Film ansehen** mit Link auf `https://www.kino-stegen.de/index.php/de/programm` ein.
- Verwendet Film-Bilder aus Cinetixx (`ARTWORK`, `ARTWORK_BIG`, `IMAGE_1` usw.), sofern die API Bildfelder liefert.
- Ergänzt optional die nächste Groundlift-Veranstaltung aus `event.event` inklusive Bild, Datum, Kurzbeschreibung und Link.
- Sendet den Newsletter per Newsletter2Go-REST-API automatisch montags um 18:00 Uhr oder manuell per Button.
- Erstellt und versendet die Presse-Mail direkt über Odoo `mail.mail` an die aus dem Projektmanagement übernommenen Presse-Adressen.
- Beide Automatiken sind pro Ausgabe per Haken steuerbar.


## Manuell Filme laden

Der Montag-17:00-Schritt kann jederzeit manuell ausgeführt werden:

- **Kino Newsletter → Einstellungen → Filme laden** lädt die Filme für die aktuelle Woche, legt bei Bedarf automatisch eine Ausgabe an und öffnet diese direkt.
- **Kino Newsletter → Ausgaben → Ausgabe öffnen → Filme laden** lädt die Filme für die ausgewählte Woche erneut und baut Newsletter- und Presse-Vorschau neu.

## Installation auf Odoo.sh

1. Ordner `gl_kino_newsletter_nl2go` in dein Odoo.sh-Repository unter `addons/` kopieren.
2. Committen und auf den gewünschten Branch pushen.
3. In Odoo Apps aktualisieren und das Modul **GROUNDLIFT Kino Newsletter Newsletter2Go** installieren.
4. Menü **Kino Newsletter → Einstellungen** öffnen und eintragen:
   - Newsletter2Go Auth-Key
   - Newsletter2Go Username
   - Newsletter2Go Passwort
   - Newsletter2Go Listen-ID
   - Absender- und Reply-Adresse
5. Button **Newsletter2Go Auth testen** ausführen.
6. Menü **Kino Newsletter → Ausgaben** öffnen und testweise **Cinetixx prüfen & Vorschau bauen** klicken.

## Automatik

Die Cronjobs laufen alle 30 Minuten, handeln aber nur in den gewünschten lokalen Zeitfenstern:

- Montag 17:00–17:59: Cinetixx prüfen und Vorschau erstellen.
- Montag 18:00–18:59: Newsletter und/oder Presse-Mail senden, wenn die jeweiligen Haken aktiv sind.

Die Zeitzone steht standardmäßig auf `Europe/Berlin`.

## Cinetixx-Interpretation

Das Modul liest die reale Cinetixx-XML-Struktur aus `GetShowInfo?mandatorID=3226381756`, unter anderem `SHOW_BEGINNING`, `SHOW_END`, `TEXT`, `BOOKING_LINK`, `ARTWORK`, `ARTWORK_BIG`, `VERANSTALTUNGSTITEL`, `SPRACHVERSION`, `VERSIONTYPE`, `SAAL`, `GENRE`, `ALTERSFREIGABE`, `SPIELDAUER_EVENT` und `STATUS`.

Wenn in einer bestehenden Konfiguration noch die alte URL mit `cinemaid`/`cinemaId` steht, versucht das Modul automatisch zusätzlich die robuste Mandator-only-URL.

## Hinweise

- Die Newsletter2Go-API erwartet OAuth2-Authentifizierung: Auth-Key wird Base64 als Basic Auth an `/oauth/v2/token` gesendet; danach werden API-Calls mit Bearer Token ausgeführt.
- Für den Versand wird ein Newsletter per `POST /lists/{list_id}/newsletters` erstellt und anschließend per `POST /newsletters/{newsletter_id}/send` übergeben.
- Falls Newsletter2Go in eurem Account Segment-/Gruppen-IDs verlangt, diese in den Einstellungen eintragen.
- Presse-Mails werden einzeln versendet, damit die Presseadressen nicht gegenseitig sichtbar sind.
