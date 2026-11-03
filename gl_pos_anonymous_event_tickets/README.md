# GROUNDLIFT – Anonyme Abendkasse für Odoo 19.sh

## Warum?
Standard-Odoo POS Event verlangt – abhängig vom Fragen-Reiter einer
Veranstaltung – für **jedes Ticket** Name/E-Mail. Diese Erweiterung ermöglicht
schnelle, nicht personenbezogene Verkäufe **ohne Änderung der Event-Fragen**.

## Verhalten
- **Standardmäßig AUS.** Der Schalter gilt **pro POS-Kasse**, nicht global.
- Wenn eingeschaltet und **kein Kunde ausgewählt** ist und die Veranstaltung
  **ausschließlich Kontaktfragen** (`name`, `email`, `phone`, `company_name`)
  hat, wird das Teilnehmerformular automatisch bestätigt.
- Pro Ticket wird als Teilnehmername eine pseudonyme technische Bezeichnung
  `Abendkasse <Zeitstempel>-<Zufall>-<laufende Nummer>` erzeugt.
- Es wird **keine fingierte E-Mail-Adresse** gespeichert, keine Telefonnummer
  angelegt und **kein neuer CRM-Kontakt** erzeugt.
- Jede Anmeldung bleibt eine echte Odoo-`event.registration` mit Odoo-Barcode.
- Der komplette Odoo-POS-Ablauf für Ticketart, Preis, Slot, Verfügbarkeit,
  Bezahlung, Registrierung, Rückerstattung und Kassensitzung bleibt bestehen.
- Wenn ein Kunde ausgewählt ist, zusätzliche Event-Fragetypen existieren oder
  die Option deaktiviert ist, öffnet sich **unverändert** das Standard-Formular.
- Online-Checkout, Gästeliste und Website werden nicht verändert.

## Installation (Odoo.sh)
1. Verzeichnis `gl_pos_anonymous_event_tickets` **unverändert** ins Root des
   bestehenden Odoo.sh-Custom-Addon-Repositories legen (neben den `gl_*`-Modulen).
2. In Git committen und zuerst auf einem **Staging-Branch** deployen.
3. Odoo > Apps > **Apps-Liste aktualisieren**, nach `Groundlift POS – Anonyme Abendkasse`
   suchen und installieren (Filter `Apps` ggf. entfernen).
4. **Kassensystem > Konfiguration > Einstellungen** öffnen, gewünschte Kasse wählen,
   unter **POS-Oberfläche** `Anonyme Abendkassen-Tickets` aktivieren und speichern.
5. Die laufende POS-Weboberfläche vollständig schließen und neu öffnen, damit
   die neue Konfiguration und JS-Assets geladen werden.
6. Staging: Testveranstaltung mit zwei Ticketarten, je 2 Stück in den Warenkorb,
   **ohne Kunden**. Es soll direkt zum Warenkorb gehen, **ohne** Name/E-Mail-Popup.
   Anschließend einen echten **Testkauf** in Staging durchführen; prüfen:
   4 Teilnehmer, je ein Barcode, richtige Preise/Steuersätze, keine Kundendaten,
   reduzierte Verfügbarkeit, Kassenumsatz und Beleg.
7. Gegenprobe: Online-Verkauf muss unverändert Namen/E-Mail verlangen.
   Gegenprobe: Kasse mit ausgewähltem Kunden muss normalen Dialog öffnen.
   Gegenprobe: Event mit zusätzlicher Pflichtfrage muss normalen Dialog öffnen.
8. Erst nach erfolgreichem Staging-Test in Production installieren.

## Not-Aus
Im betroffenen POS die Option deaktivieren und POS neu öffnen. Danach ist die
ursprüngliche Odoo-19-Teilnehmerabfrage wieder aktiv. **Keine Datenmigration**.

## Einordnung / Einschränkungen
- Ein neutraler Teilnehmername ist keine Angabe zur tatsächlichen Identität.
  Einzelne Registrierungen sind anhand ihrer Odoo-Barcodes unterscheidbar.
- Werden zusätzliche Registrierungsfragen (z.B. Einwilligung, Altersprüfung,
  Allergieabfrage) ergänzt, bleibt das **gesamte** Formular unverändert erhalten.
- Falls beim Checkout ein **Kunde explizit zugeordnet** wurde, bleibt das
  Standardformular bestehen. Für eine Rechnung können Kundendaten erforderlich sein.
- Die Funktion ersetzt keine Server-Verfügbarkeits-/Zahlungsprüfung.
- Der hier gelieferte Code wurde statisch geprüft; ein echtes POS-Staging-System
  ist zur Laufzeitprüfung notwendig. Im ZIP sind **keine Änderungen** an
  bestehenden Groundlift-Modulen enthalten.

## Kompatibilitätsprüfung gegen Production-ZIP vom 29.10.2026
- `gl_event_guestlist`: erweitert `event.registration.create`/`write` für
  Kapazitätsprüfung; **nicht verändert**. POS verwendet dieselbe Registrierung.
- `groundlift_event_checkout`: nur Website/Payment-Routen/Assets;
  **nicht verändert**.
- `gl_event_cleverreach_optin`: nur bei ausdrücklich gesetztem Newsletter-Opt-in;
  keine E-Mail, kein neuer Opt-in.
- `gl_gross_sales_price`: patched `PosOrderline.setUnitPrice`;
  **nicht verändert**.
- `gl_pos_draft_cleanup`, `gl_pos_closing_tips`: POS-Abschluss-/Cleanup-Funktionen;
  **nicht verändert**.
- `groundlift_kino_pos`: eigenes Kinosystem, nicht `pos_event`-Popup;
  **nicht verändert**.

Technische Stelle: Patch von `@pos_event/app/components/popup/event_registration_popup/event_registration_popup`
auf den Odoo-19.0-Stand; kein Patch von `ProductScreen`, `pos.order` oder `event.registration`.
