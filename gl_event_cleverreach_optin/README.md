# Groundlift Event CleverReach Opt-In – Odoo 19 SH

Erweiterungsmodul für die bestehende Groundlift-CleverReach-Integration
`gl_cleverreach_newsletter`.

## Funktionen

- Checkbox direkt im Odoo-Ticket-Popup:
  **„Ich möchte auch über andere Veranstaltungen informiert werden - Friendly Newsletter: Nervt nicht, informiert!“**
- Die Checkbox ist – wie beauftragt – standardmäßig aktiviert.
- Wird sie vom Gast deaktiviert, wird für diese Anmeldung **kein** CleverReach-Empfänger angelegt.
- Bei kostenlosen/normalen Anmeldungen erfolgt die Übertragung nach erfolgreicher Anmeldung.
- Bei kostenpflichtigen Tickets erfolgt die Übertragung erst nach Bestätigung des Verkaufsauftrags; ein bloß gestarteter Checkout reicht nicht.
- Vor jedem Live-Upload wird anhand der normalisierten E-Mail-Adresse in `Newsletter_allgemein` auf ein vorhandenes CleverReach-Mitglied geprüft.
- Vorhandene Empfänger werden nicht überschrieben und nicht erneut aktiviert.
- Vorname/Nachname werden aus dem Odoo-Teilnehmernamen auf die globalen CleverReach-Felder `firstname` / `lastname` abgebildet; fehlende Felder legt das Modul beim ersten Bedarf an.
- CleverReach-Fehler dürfen Anmeldung oder Bezahlung niemals verhindern. Der Fehler wird am `event.registration`-Datensatz protokolliert.
- Nutzt vollständig die bereits vorhandene Authentifizierung und `_api()`-Methode aus `gl_cleverreach_newsletter`; keine zweiten API-Zugangsdaten nötig.

## Bestandsimport

In **CleverReach Newsletter → Einstellungen** erscheint der Button:

**Alle bisherigen Teilnehmer bei CleverReach eintragen**

Ablauf:

1. Zielgruppe `Newsletter_allgemein` auflösen; falls nötig CleverReach-Listen neu importieren.
2. Alle bestätigten/erledigten `event.registration` mit E-Mail lesen (auch archivierte Datensätze).
3. E-Mails normalisieren und Odoo-interne Dubletten zusammenfassen.
4. Vor irgendeinem Upload alle vorhandenen Empfänger der CleverReach-Gruppe laden und gegenprüfen.
5. Nur fehlende E-Mail-Adressen über CleverReach `/receivers/insert` in Stapeln bis 1000 Datensätze übertragen.
6. Falls ein Stapel fehlschlägt, einzeln fortsetzen, damit eine problematische Adresse nicht den ganzen Import stoppt.
7. Erst wenn alles ohne offene Fehler durchgelaufen ist, wird der Bestandsimport als einmalig abgeschlossen markiert.
8. Bei einem Teilfehler kann der Button erneut geklickt werden; bereits erfolgreiche Empfänger werden durch die erneute Dublettenprüfung übersprungen.

Wichtig: Der Bestandsimport setzt bei alten Odoo-Registrierungen **keine erfundene Opt-in-Checkbox** und keinen erfundenen historischen Einwilligungszeitpunkt. Er ist eine bewusst vom Administrator ausgelöste Migration.

## Installation in Odoo SH / GitHub

1. ZIP herunterladen und entpacken.
2. Den kompletten Ordner `gl_event_cleverreach_optin` in dasselbe Odoo-SH-Repository legen, in dem auch `gl_cleverreach_newsletter` liegt (z. B. unter `custom_addons/`).
3. Dateien per GitHub Web hochladen und committen.
4. Odoo-SH-Build abwarten.
5. In Odoo die App-Liste aktualisieren.
6. **Groundlift Event CleverReach Opt-In** installieren.
7. **CleverReach Newsletter → Einstellungen** öffnen.
8. Prüfen, dass **Event-Teilnehmer: CleverReach-Liste** exakt `Newsletter_allgemein` lautet.
9. Einmal **Listen importieren** ausführen, falls die Liste noch nicht in Odoo sichtbar ist.

## Funktionstest

### Neue kostenlose Anmeldung

1. Eventseite öffnen und Ticket-Popup aufrufen.
2. Checkbox aktiviert lassen.
3. Anmeldung abschließen.
4. In CleverReach prüfen: E-Mail in `Newsletter_allgemein`, samt `firstname` / `lastname`.

### Opt-out

1. Zweite Testadresse verwenden.
2. Checkbox im Popup deaktivieren.
3. Anmeldung abschließen.
4. Die Adresse darf nicht zu `Newsletter_allgemein` hinzugefügt werden.

### Kostenpflichtiges Ticket

1. Ticket mit Checkbox starten.
2. Vor Abschluss der Zahlung darf noch keine neue CleverReach-Anlage durch dieses Modul stattfinden.
3. Bestellung/Zahlung abschließen, sodass der Odoo-Verkaufsauftrag bestätigt ist.
4. Danach muss der Empfänger übertragen bzw. als bereits vorhanden erkannt werden.

## Datenschutz-Hinweis

Das Modul setzt die Checkbox auf ausdrücklichen Wunsch standardmäßig auf „angehakt“ und enthält außerdem einen manuellen Import historischer Teilnehmer. Ob diese Gestaltung bzw. der Bestandsimport für eure konkrete Newsletter-Nutzung die erforderliche Rechtsgrundlage/Einwilligung erfüllt, ist eine organisatorisch-rechtliche Frage und wird vom Modul nicht behauptet. Für den Bestandsimport zeigt Odoo deshalb vor Ausführung zusätzlich einen Bestätigungsdialog.
