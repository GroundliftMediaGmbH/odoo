# Groundlift Servicepersonal 19.0.2.0.13 – Einzelabsagen + Rücknahme der Verfügbarkeit

## 1. Backend: „Absagen“ neben „Fest buchen“
- In der Personalliste auf der Serviceschicht (sowie in der Zuteilungsliste und im Zuteilungsformular) kann eine **verfügbare, nicht fest gebuchte** Person einzeln abgesagt werden, **auch wenn noch Personalbedarf offen ist**.
- Sicherheitsabfrage vor der Aktion. Nur interne Odoo-Nutzer mit Schreibrecht auf die Schicht dürfen die Aktion ausführen.
- Status wird `not_selected` mit Grund `manual` (nicht `declined`, denn die Person hat *nicht selbst* abgesagt). Festbuchungen sind ausdrücklich geschützt.
- Antwort-Token wird neu erzeugt, alte Links können eine manuelle Absage nicht mehr rückgängig machen. Automatische Sammelanfragen überspringen manuell abgesagte Kandidaten (individuelles erneutes Mailen bleibt möglich). Veraltete, noch offene Mail-Freigaben zu dieser Verfügbarkeit werden verworfen.
- Neue neutrale E-Mail-Vorlage `Servicepersonal: Manuelle Absage einer Verfügbarkeit` – sagt nicht irreführend „Schicht bereits vollständig besetzt“.
- Versand läuft wie gewohnt über die vorhandene Mail-Freigabe, falls diese aktiv ist. Ohne E-Mail-Adresse erfolgt nur die Statusänderung mit Hinweis.
- Die vorhandene automatische Absage bei vollständiger Besetzung und der bisherige Absage-Assistent bleiben erhalten.

## 2. Mitarbeiterportal: „Ich bin doch nicht verfügbar“
- Erscheint **nur bei verfügbar gemeldeten, nicht fest gebuchten Einsätzen** (inklusive verfügbarer Altdaten).
- Eigene POST-Aktion mit CSRF-Schutz und Prüfung des über PIN angemeldeten Mitarbeiters gegen die Schichtzuordnung.
- Nach Bestätigung: Status `declined`, Auswahl zurückgesetzt, Zeitstempel gespeichert, alte Antwortlinks entwertet, Erfolgsmeldung im Portal; gebuchte Einsätze werden nicht aufgehoben.
- Die bestehende Seite zeigt bei einer manuellen Absage durch das Groundlift-Team künftig „Nicht eingeplant“ statt „Schicht besetzt“.

## Installation
ZIP entpacken und den enthaltenen `gl_service_staff`-Ordner im Odoo.sh Git-Repository ersetzen; committen und Modul **Groundlift Servicepersonal** im Apps-Menü aktualisieren. Zunächst in Staging testen. Kein Datenbank-Löschschritt nötig.
