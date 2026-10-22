# Groundlift Servicepersonal – Update 19.0.2.0.8

Basis: 19.0.2.0.7, bestehende Schnittstellen, Modelle und E-Mail-Freigabewarteschlange bleiben bestehen.

## Neue Funktionen

1. Mitarbeiter-Portal `/servicepersonal`: Kolleginnen/Kollegen werden je Einsatz nur angezeigt, wenn sie bereits fest gebucht sind (state=accepted, role=desired). Ohne Kontakt-/Personaldaten. Duplikate derselben HR-Person werden ausgeblendet.
2. Privates Kalenderabonnement via `/servicepersonal/kalender/<member_id>/<random>.ics`, mit stabilem UID je Zuteilung. Kalender enthält nur fest gebuchte, aktive eigene Schichten; Datum in UTC (`Z`), lokale Umrechnung durch Kalenderanbieter. Link einmal **per URL abonnieren**, nicht einmalig importieren. Kalenderanbieter kontrollieren Abrufintervall; Google kann Stunden benötigen. Token bei Bedarf über den Mitarbeiter-Formularknopf erneuern (alter Feed wird sofort ungültig).
3. Zeitzonenfix: Mailzeiten werden unabhängig von Cron-/OdooBenutzer-Zeitzone immer in `Europe/Berlin` (MESZ/MEZ) formatiert. Vorhandene, individuell angepasste Mailvorlagen prüfen, falls sie Rohfelder statt `mail_start_display` und `mail_end_display` verwenden.
4. Sobald `required_count > 0` und die Anzahl fest gebuchter Mitarbeiter mindestens dem Bedarf entspricht, werden noch offene **Verfügbar-Meldungen** ohne feste Buchung genau einmal als `not_selected` markiert. Automatische Absage über die normale Mailvorlage und Mail-Freigabe. Keine Absagen für noch ungeantwortete Einladungen oder gebuchte Personen. Bereits versendete Mails können nicht zurückgerufen werden. Beim Wiederöffnen der Kapazität bleibt eine bereits versandte Absage bestehen; für eine neue Anfrage muss die betroffene Person erneut eingeladen werden.
5. Chronologische Portalansicht nutzt pro Zuordnung `planned_start_datetime`, sonst `shift.start_datetime`, sonst `shift_date`. Dadurch stehen Projekte zwischen den Veranstaltungen am richtigen Datum.

## Installation

Staging: Modulordner ersetzen, App `Groundlift Servicepersonal` aktualisieren, bestehenden Mail-Debugmodus **aktiv lassen** und Test durchführen.

## Abnahmetests

- Person A/B fest buchen, Person C meldet sich verfügbar: wenn Bedarf erfüllt, C wird einmalig auf `Schicht besetzt` gesetzt und erhält Freigabe-Mail.
- Zeitzonen-Test: Termin 24.10. 17:30 lokal ergibt in der Vortagsmail `24.10.2026 17:30 Uhr`; ebenso Wintertermin 17:30 Uhr (keine +1/+2 Abweichung).
- Portal: Projekte und Veranstaltungen chronologisch; nur gebuchte Teamkollegen sichtbar, eigene Person nicht doppelt.
- Google Kalender: `Weitere Kalender > Per URL` und https-ICS-Link einsetzen; Dienst verschieben und auf Aktualisierung des bestehenden Kalendereintrags warten.
- Token erneuern: alter Link 404, neuer Link abrufbar.

Hinweis: Kein Odoo.sh-Live-Lauf in dieser Umgebung verfügbar. Syntax/XML und iCal-Feed können lokal getestet werden, vollständige Workflow-Abnahme auf Staging erforderlich.

Upgrade 19.0.2.0.8 erzeugt fehlende Kalender-Token für bereits bestehende Mitarbeiter ohne E-Mail-Versand. Der Zugriff über die Mitarbeiter-Seite stellt fehlende Token bei Bedarf ebenfalls bereit. Es erfolgt keine rückwirkende Absage bestehender vollständig besetzter Schichten.
