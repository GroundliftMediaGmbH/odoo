# Changelog

## 19.0.1.0.3

- Odoo-19-Feld `employee_type` der aktuellen Mitarbeiterversion wird ausgewertet.
- Automatische Erkennung berücksichtigt Vertragsarten, Beschäftigungsarten, Tags und passende Studio-Felder.
- Import zeigt gefundene Anwesenheiten, Mitarbeiter, übernommene und ausgeschlossene Personen an.
- Warnung mit Diagnose, wenn Anwesenheiten existieren, aber keine Minijobber erkannt werden.
- Sudo-Recordset beim Gruppieren der Anwesenheiten vereinheitlicht.

## 19.0.1.0.2

- Odoo-Systemadministratoren erhalten die Modul-Verwaltungsgruppe automatisch als implizite Gruppe.
- Das Root-Menü besitzt nun direkt die Aktion „Prüfmonate“ und erscheint dadurch zuverlässig als App auf dem Odoo-Desktop.
- Bestehende Installationen erhalten die Korrektur beim Modul-Upgrade.

## 19.0.1.0.1

- Installationsfehler in der Suchansicht behoben
- Monatsstatusfelder `all_approved` und `all_paid` als gespeicherte, durchsuchbare Felder definiert
- Abhängigkeiten der Monatszusammenfassung für neue, entfernte und geänderte Mitarbeiterzeilen präzisiert

## 19.0.1.0.0

- Erstversion für Odoo 19 SH
- Geschütztes Prüfportal
- Odoo-Benutzer oder freie Zugangsdaten
- Prüferstufe 1 und 2
- Sekundengenaue Monats- und Tagesberechnung
- Automatische 30-Minuten-Pause bei mehr als sechs Stunden
- Zweistufige Tagesfreigabe
- Überwiesen-Status je Mitarbeiter-Monat und für den gesamten Prüfmonat durch Prüfer 2
- Monats- und Prüfhistorie
- Automatische Vormonatserstellung und E-Mail am 1. des Folgemonats
