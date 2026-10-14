# Groundlift Schnell-Notiz (Odoo 19 SH)

Technischer Modulname: `gl_quick_note` — Version 19.0.1.0.1

## Installation

1. Verzeichnis `gl_quick_note` (direkt aus der ZIP) auf derselben Ebene wie die anderen Groundlift-Module ins Odoo-SH-Git-Repository kopieren.
2. Staging-Branch deployen und **Apps → Apps-Liste aktualisieren**.
3. Nach **Schnell-Notiz** suchen und installieren. Voraussetzung: `project`, `crm`, `event`, `mail`, `gl_project_checklist`.
4. App **Schnell-Notiz** öffnen. Der Editor startet über **Neue Notiz**.
5. Optional als Administrator über **Schnell-Notiz → Einstellungen** den **OpenAI API-Schlüssel** und das Modell (Standard: `gpt-4.1-mini`) hinterlegen und speichern. Der API-Schlüssel bleibt in Odoo-Systemparametern, nicht im ZIP.
6. Zuerst in Staging mit anonymisierten Testnotizen, bestehendem Projekt, neuem Projekt, bestehendem CRM-Eintrag, neuem CRM-Eintrag und Veranstaltung testen.

## Funktionen

- **Ein großer HTML-Editor** im Odoo-Backend mit Odoo-Standardformatierungen.
- **In Projekt speichern:** Bestehendes Projekt wählen oder ein neues Projekt benennen. Bei erreichbarer OpenAI API werden belegte Angaben auf passende `gl_`- und `x_studio_`-Felder sowie vorhandene reguläre Projekt-Datumsfelder verteilt (Text, Zahlen, Datum, Auswahl), einschließlich `gl_check_reception`, `gl_check_schedule_line_ids` und `gl_media_rundown_line_ids`. Alte Projektbeschreibung wird nicht ersetzt: Zusammenfassung und Änderungen werden am Ende angefügt. Gleiche Ablaufzeilen werden nicht doppelt erzeugt.
- **Ohne API / bei Fehler:** Originalnotiz wird statt der KI-Zusammenfassung in die Projektbeschreibung übernommen. Vorhandener Inhalt bleibt davor erhalten.
- **In CRM speichern:** Vorhandenen Eintrag auswählen oder neuen Eintrag in der bereits existierenden CRM-Phase `Neu` erzeugen. API-extrahierte Kundendaten werden nur mit überprüfbarer Textstelle übernommen. Fehlende manuelle Pflichtangaben müssen im Wizard ergänzt werden. Beim bestehenden CRM-Eintrag wird die neue Notiz ganz oben in `description` eingefügt.
- **In Veranstaltung speichern:** Als interne Odoo-Chatter-Notiz (`mail.mt_note`) hinterlegt, keine öffentliche Antwort.
- **Übertragungsprotokoll:** Originalnotiz, Ziel, KI-Status, Änderungen; normale Benutzer sehen nur ihre eigenen Einträge, Systemadministratoren alle.

## KI-Sicherheitsregeln

- Der Originaltext ist untrusted input. Die KI bekommt nur den Notiztext und eine Liste zulässiger Feldnamen (keine bestehenden Projektdaten).
- Ein Feldwert wird nur übernommen, wenn ein exaktes Zitat aus der Notiz als Beleg mitgeliefert wird. Zahlen im Zielwert müssen in diesem Zitat vorkommen.
- Eine Zusammenfassung wird aus belegten **Originalzitaten**, kategorisiert nach Kundendaten/Gastro/Ablauf/Technik/Organisation/Sonstiges, aufgebaut, nicht aus einem freien KI-Fließtext.
- **Nicht automatisch bearbeitet:** binäre Felder, Zeichnungen, relationale Fremdschlüssel, Berechtigungen, interne Berechnungsfelder, Legacy-Ablaufnummern, technisches Projekt-ID-/Statusmanagement. Diese sind aus einer freien Notiz nicht zuverlässig aktualisierbar. Änderungen an solchen Feldern bleiben manuelle Aufgabe.
- Die KI kann bei der semantischen Zuordnung trotz Belegprüfung falsch liegen; insbesondere bei kritischen Terminen und Kundenzahlen gilt menschliche Kontrolle.
- Bei aktivierter KI wird der Notiztext an **OpenAI** gesendet. Datenschutzrechtliche Freigabe und organisatorische Zustimmung vor Verwendung von Kunden-/Personendaten prüfen.
- API-Aufrufe haben einen Timeout von 15 Sekunden. Netzwerkfehler oder ungültige API-Antworten führen zum beschriebenen Fallback.

## Testumfang und Grenzen

Im Paket liegen Odoo-Transaktionstests (`tests/test_quick_note.py`): alter Projekttext bleibt stehen, Sektempfang + Ablaufzeile, alte CRM-Notizen bleiben erhalten. Die Paketstruktur, alle Python-Dateien und XML-Dateien sowie zentrale Zuordnungs-/Duplikat-Logik wurden lokal geprüft. **Ein echter Odoo-19-SH-Installations- und Browser-Test ist in dieser Entwicklungsumgebung nicht möglich** und muss auf Staging stattfinden.

## Besonderheiten

- Es wird kein neuer `res.partner` ohne explizite Benutzerentscheidung angelegt; CRM-Kundendaten stehen zunächst am Lead / an der Opportunity.
- Bestehende CRM-Felder dürfen durch neue ausdrücklich eingegebene oder belegte Daten aktualisiert werden; alte CRM-Beschreibung bleibt vollständig bestehen.
- In einer Projektnotiz erkannte Änderungen können vorhandene zugehörige Fachfelder aktualisieren. Die alte Fachfeldbelegung wird in der Beschreibungs-Änderungsliste dokumentiert. Bei Unsicherheit vor Produktivverwendung in Staging prüfen.
- Einrichten und Ändern des Schlüssels ist nur für Systemadministratoren möglich.


## Korrektur v1.0.1 (14.10.2026)

- **Installationsfehler behoben:** Die `ir.actions.act_window`-Aktion `action_gl_quick_note_settings` verwendete `target="inline"`. Dieser Wert ist unter Odoo 19 kein zulässiger `ir.actions.act_window.target`-Wert und verursachte bei der Installation einen `RPC_ERROR` (`Wrong value ... 'inline'`). Der Wert ist nun `current`.
- An der Datenstruktur und an bestehenden Projekten, CRM-Einträgen oder Veranstaltungen wurden durch dieses reine XML-Fix keine Änderungen vorgenommen.
- Installation weiterhin zunächst in Staging prüfen. Eine laufende Odoo-19-Instanz steht für vollständige Installationstests nicht zur Verfügung.
