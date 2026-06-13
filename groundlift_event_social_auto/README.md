# Groundlift Event Social Automation

Version: 19.0.1.0.4

Dieses Odoo-19-SH-Modul erzeugt automatisch bearbeitbare Social-Marketing-Posts aus Veranstaltungen.

## Hauptfunktionen

- Trigger: Veranstaltung erreicht die konfigurierbare Phase `Angekündigt`.
- Erstpost am Folgetag zur konfigurierten Uhrzeit.
- Reminder-Post vor der Veranstaltung.
- Eventtag-Post am Veranstaltungstag.
- Ausverkauft-Post mit Anpassung/Entfernung künftiger Werbeposts.
- Nachbericht-Post, wenn die Veranstaltung die konfigurierbare Abschlussphase erreicht.
- Alle Texte/Headlines sind in der App konfigurierbar.
- Button `Alle Events laden`: erzeugt Posts für alle bereits angekündigten künftigen Veranstaltungen.
- Kollisionsschutz: pro Kalendertag wird nur ein automatisch erzeugter Groundlift-Post geplant.
- Prioritäten: Eventtag/Ausverkauft/Nachbericht/Reminder haben Vorrang vor Erstankündigung; Erstankündigungen werden verschoben.
- ChatGPT/OpenAI API kann automatisch zusätzliche Hashtags erzeugen.
- Optionale Lückenfüller-Posts: Wenn in einem Zeitraum keine Eventposts geplant sind, wird ein werbender Post aus Homepage-Bild + Homepage-Kontext erzeugt.

## Bildlogik

Für Eventposts wird ausschließlich `event.event.x_studio_website_header` verwendet.
Es gibt keinen Fallback auf andere Bildfelder.

Lückenfüller-Posts verwenden Bilder von der konfigurierten Homepage, standardmäßig `https://www.groundlift.de`.

## Konfiguration

Nach Installation:

1. Event Social Automation → Einstellungen öffnen.
2. Facebook-/Instagram-Social-Accounts auswählen.
3. OpenAI API Key hinterlegen, falls KI-Hashtags/Lückenfüller genutzt werden sollen.
4. Textbausteine prüfen.
5. Freigabe-Automatik anfangs deaktiviert lassen.
6. Optional: Lückenfüller-Posts aktivieren.

## OpenAI / ChatGPT API

Die App nutzt serverseitig die Chat Completions API unter `https://api.openai.com/v1/chat/completions`.
Ohne API Key läuft das Modul weiter, nutzt dann aber nur lokale/standardisierte Hashtags und Fallback-Texte.

## Hinweise

- Social Posts bleiben normale `social.post`-Datensätze und können in Odoo Social Marketing bearbeitet werden.
- Bei aktivierter Freigabe-Automatik werden Posts direkt in Odoo geplant.
- Wenn manuelle Freigabe aktiv ist, bleiben Posts als Entwurf/Freigabe erforderlich stehen.
- Bitte zuerst auf Staging installieren und testen.
