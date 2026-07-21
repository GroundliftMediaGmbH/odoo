# Changelog

## 19.0.1.0.6

- Prüfportal visuell an das Groundlift Mitarbeiter-Stundenportal angeglichen.
- Eigenständige, dunkel gestaltete und vollständig gekapselte CSS-Oberfläche ergänzt.
- Website-Header und -Footer werden auf den Prüfseiten ausgeblendet, damit das aktive Odoo-Theme die Darstellung nicht mehr beeinflusst.
- Bootstrap-Accordion durch native, theme-unabhängige `<details>`-Elemente ersetzt.
- Tabellen, Formulare, Statusanzeigen und Buttons für Desktop und Mobilgeräte neu gestaltet.
- Direktes Öffnen des zuletzt bearbeiteten Mitarbeiters nach dem Speichern ergänzt.

## 19.0.1.0.5

- Importfilter greift nun direkt auf das technische Feld `structure_type_id` zu.
- Maßgeblich ist die am Anwesenheitstag gültige Odoo-19-Mitarbeiterversion (`hr.version`).
- Ausschließlich die Strukturtyp-Namen **Minijob** und **Geringfügige Beschäftigung** werden akzeptiert.
- Fehleranfällige Erkennung über Feldnamen oder Feldbeschriftungen entfernt.
- Importdiagnose zeigt den konkreten Wert aus `structure_type_id` an.

## 19.0.1.0.4

- Importfilter strikt auf das Feld **Zahlungskategorie** begrenzt.
- Es werden ausschließlich die Werte **Minijob** und **Geringfügige Beschäftigung** akzeptiert.
- Erkennung über Mitarbeiter-Tags, Jobtitel, Vertragsart, allgemeine Beschäftigungsart oder manuelle Modul-Auswahl entfernt.
- Historische Zahlungskategorie wird nach Möglichkeit aus der am Anwesenheitstag gültigen Odoo-19-Mitarbeiterversion gelesen.
- Diagnose nennt nun den tatsächlichen Zahlungskategoriewert oder meldet ein fehlendes/leeres Feld.

## 19.0.1.0.3

- Erweiterte Erkennung von Beschäftigungsarten in Odoo 19.
- Importdiagnose ergänzt.

## 19.0.1.0.2

- App-Menü für Administratoren sichtbar gemacht.

## 19.0.1.0.1

- Gespeicherte Monatsstatusfelder für Suchfilter ergänzt.

## 19.0.1.0.0

- Erstveröffentlichung.
