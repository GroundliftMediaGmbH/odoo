# Groundlift Event Social Automation für Odoo 19.sh

Dieses Modul erzeugt aus Odoo-Veranstaltungen automatisch Social-Marketing-Posts für Facebook/Instagram.

## Funktionsumfang

- Trigger: Veranstaltung erreicht die Phase **Angekündigt**.
- Erstpost: Folgetag um 10:00 Uhr.
- Reminder: 3 Tage vor der Veranstaltung um 10:00 Uhr.
- Eventtag-Post: am Veranstaltungstag um 10:00 Uhr.
- Ausverkauft-Logik:
  - erzeugt einen Ausverkauft-Post 1 Stunde nach Erkennung,
  - entfernt den 3-Tage-Werbepost, sofern noch nicht veröffentlicht,
  - ersetzt den Eventtag-Werbepost durch einen Ausverkauft-/Volles-Haus-Post.
- Anfangs Freigabe erforderlich:
  - neue Posts werden als bearbeitbare Entwürfe mit gewünschtem Planungsdatum erzeugt,
  - per Button können Posts freigegeben und geplant werden,
  - global kann später automatische Planung ohne manuelle Freigabe aktiviert werden.
- Event-Headerbild wird aus `x_studio_website_header`, `website_image` oder Standard-Eventbildern übernommen.
- Ticketlink wird aus `website_url` bzw. Event-URL erzeugt.
- Standard-Hashtags und Event-Tags/Kategorien werden ergänzt.

## Installation in Odoo.sh

1. ZIP entpacken.
2. Den Ordner `groundlift_event_social_auto` in euer Odoo.sh Custom-Addons-Repository kopieren.
3. Commit & Push nach Staging.
4. Apps aktualisieren.
5. App **Groundlift Event Social Automation** installieren.
6. Menü **Event Social Automation → Einstellungen** öffnen.
7. Facebook- und Instagram-Social-Accounts von `groundlift studio` auswählen.
8. `Posts ohne manuelle Freigabe automatisch planen` zunächst deaktiviert lassen.
9. In Staging mit einer Testveranstaltung testen.

## Hinweise

- Voraussetzung ist die Odoo Social Marketing App (`social`) mit bereits verknüpften Facebook-/Instagram-Kanälen.
- Die Posts werden als normale `social.post`-Datensätze angelegt und können in Odoo Social Marketing bearbeitet werden.
- Das Modul ist bewusst defensiv gebaut: Bei fehlenden Social Accounts oder fehlenden Eventdaten wird das Event nicht blockiert, sondern ein Hinweis am Event gespeichert.
- Da Odoo Social Marketing Enterprise-Code ist, nutzt das Modul Laufzeitprüfungen für mehrere Feldnamen, wo möglich.

## Wichtige Konfiguration

- Auslösende Veranstaltungsphase: `Angekündigt`
- Fallback-Suche nach Social Accounts: `groundlift studio`
- Standard-Hashtags: `#groundlift #ammersee #livemusik`
- Kampagne: `Öffentliche Veranstaltungen`
- Zeitzone: `Europe/Berlin`
