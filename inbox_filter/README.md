# Inbox Filter für Odoo 19 SH

GPT-gestützte Sortierung von CRM-Datensätzen aus der Phase **Neu**.

## Funktionen

- CRM-Schnellzugriff: **Sortieren** und **Inbox Filter öffnen**.
- Eigene App **Inbox Filter** mit Prompt-Tabs für:
  - Qualifiziert
  - SPAM
  - Projekt/VA
  - ToDo
  - Kundensupport
  - Zu prüfen
- Einstellungen für OpenAI API Token, Modell, API-URL und Sortierlimit.
- Historie aller Sortiervorgänge mit Snapshot des ursprünglichen CRM-Datensatzes.
- Manuelle Korrekturen:
  - Rückgängig
  - SPAM bestätigt
  - Qualifiziert
  - Projekt/VA
  - ToDo
  - Kundensupport
- Live-Lernlogik: Bei manuellen Korrekturen wird per GPT eine kurze Regel erzeugt und dem passenden Filterprompt als Lernbeispiel hinzugefügt.

## Sicherheitslogik

SPAM, Projekt/VA, ToDo und Kundensupport werden nicht sofort hart aus der Datenbank gelöscht. Der CRM-Datensatz wird zunächst archiviert und bleibt über die Historie rückgängig machbar. Nur **SPAM bestätigt** löscht den ursprünglichen CRM-Datensatz endgültig.

## Version 19.0.1.0.2

- Odoo-19-kompatible Search-View korrigiert: Das `<group>`-Element in Search-Views enthält keine Attribute mehr.
- Sicherheitsgruppe bleibt ohne `category_id`, damit die Installation in Odoo 19 SH funktioniert.

## Installation auf Odoo.sh

1. ZIP entpacken oder Ordner `inbox_filter` in dein Custom-Addons-Repository kopieren.
2. Auf Odoo.sh committen und builden.
3. Apps-Liste aktualisieren.
4. App **Inbox Filter** installieren.
5. Interne Benutzer können **Inbox Filter** verwenden. Nur Administratoren sehen die Einstellungen.
6. In **Inbox Filter > Einstellungen** den OpenAI API Token eintragen.

## Hinweise

- Das Modul nutzt bewusst `urllib` statt des Python-OpenAI-SDKs, damit keine zusätzlichen Python-Abhängigkeiten auf Odoo.sh nötig sind.
- Standardmodell: `gpt-4.1-mini`. Das Modell ist in den Einstellungen änderbar.
- Für Kundensupport-Tickets wird `helpdesk.ticket` verwendet, wenn Helpdesk installiert ist. Ist Helpdesk nicht installiert, gibt das Modul eine klare Fehlermeldung aus.
- Für ToDos muss der ausgewählte Mitarbeiter mit einem Odoo-Benutzer verknüpft sein.


## Änderung 19.0.1.0.1

- Odoo-19-Kompatibilitätsfix: keine Verwendung von `res.groups.category_id` mehr.
- XML-Ladereihenfolge korrigiert: Das Hauptmenü wird vor den Untermenüs geladen.
