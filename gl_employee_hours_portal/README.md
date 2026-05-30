# GROUNDLIFT Mitarbeiter-Stundenportal

Odoo 19 SH Modul für eine öffentliche Mitarbeiterseite ohne Odoo-Benutzerkonto.

## Funktionen

- Mitarbeiter registrieren sich selbst mit ihrer in Odoo hinterlegten Arbeits-E-Mail (`hr.employee.work_email`).
- Registrierung wird per E-Mail-Aktivierungslink bestätigt.
- Kein `res.users`-Login notwendig; eigene Session für das Stundenportal.
- Monatsübersicht der eigenen Anwesenheiten aus `hr.attendance`.
- Navigation vor/zurück durch Monate.
- Anzeige von Arbeitstag, Startzeit, Endzeit, Dauer je Eintrag, Tagessumme und Monatssumme.
- Nicht gearbeitete Tage werden nicht angezeigt.
- Offene Anwesenheiten ohne `check_out` werden angezeigt, aber nicht in die Summe eingerechnet.
- Passwort-vergessen-Funktion mit E-Mail-Link.

## Öffentliche URLs

- `/mitarbeiter/stunden` – Monatsübersicht nach Login
- `/mitarbeiter/stunden/login` – Login
- `/mitarbeiter/stunden/registrieren` – Registrierung
- `/mitarbeiter/stunden/passwort-vergessen` – Passwort zurücksetzen

## Installation in Odoo SH

1. Ordner `gl_employee_hours_portal` in dein Custom-Addons-Repository kopieren.
2. Committen und auf den gewünschten Branch pushen.
3. In Odoo Apps-Liste aktualisieren.
4. Modul `GROUNDLIFT Mitarbeiter-Stundenportal` installieren.
5. Sicherstellen, dass bei allen relevanten Mitarbeitern im Mitarbeiterprofil eine Arbeits-E-Mail hinterlegt ist.
6. Sicherstellen, dass ausgehende E-Mails in Odoo funktionieren.

## Zeitzone

Standardmäßig wird `Europe/Berlin` verwendet. Anpassbar über den Systemparameter:

`gl_employee_hours_portal.timezone`

## Datenbasis

Das Modul nutzt die Standard-Anwesenheiten aus `hr.attendance`:

- `employee_id`
- `check_in`
- `check_out`

Die Anzeige ist rein lesend. Mitarbeiter können keine Zeiten ändern.
