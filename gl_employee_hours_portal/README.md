# GROUNDLIFT Mitarbeiter-Stundenportal – Odoo 19 SH

Version **19.0.1.1.1** (Update des bestehenden Moduls, Daten bleiben erhalten).

## Neu: Zugangsdatenverwaltung für Odoo-Nutzer

Unter **Stundenportal → Mitarbeiter-Konten** gibt es für jedes registrierte Konto:

- **Persönlicher Login-Link**: führt zur Anmeldung mit vorbelegter E-Mail-Adresse. Der Link ersetzt **nicht** das Passwort.
- **Passwort gesetzt**: zeigt an, ob bereits ein Passwort-Hash existiert.
- **Passwort selbst setzen**: manuell ein neues Passwort (mindestens acht Zeichen) wählen.
- **Zufallspasswort erzeugen**: sicheres Passwort generieren, **nur einmal** in einer dauerhaft geöffneten Odoo-Benachrichtigung anzeigen und direkt kopieren.
- **Reset-Link mailen**: sendet der registrierten Person bei aktivem Konto einen Link zum selbständigen Zurücksetzen.
- **Portal öffnen**: öffnet den individuellen Login-Link in einem neuen Tab.

**Wichtig:** Bisherige Passwörter lassen sich *nicht* auslesen. Die Originalversion speichert einen Einweg-Hash (PBKDF2-SHA256), keinen Klartext. Auch die neue Version speichert keine dauerhaft abrufbaren Klartextpasswörter.

## Berechtigungen

- Bestehende Nutzergruppen **Personalverwaltung / Manager** (`hr.group_hr_manager`) und **Einstellungen / Administrator** (`base.group_system`) dürfen die Zugänge wie bisher verwalten.
- Zusätzlich gibt es die Odoo-19-Berechtigungsgruppe **GROUNDLIFT Stundenportal → Mitarbeiter-Zugänge verwalten**. Diese kann einem normalen internen Odoo-Nutzer zugewiesen werden, ohne ihm Vollzugriff auf die Mitarbeiterstammdaten zu geben. Sie kann Portal-Konten ansehen sowie neue Passwörter setzen oder Reset-Mails versenden, jedoch Konten nicht löschen oder sperren.
- **Andere Odoo-Nutzer und Website-Besucher haben keinen Zugriff** auf die Verwaltungsansicht. Nicht für alle internen Nutzer freischalten: die Berechtigung ist sicherheitsrelevant.
- Tokens und Hashes sind über Feldgruppen auf Odoo-Systemadministratoren begrenzt.

## Passwortwechsel & Sessions

Bei jedem Passwortwechsel werden die vorherigen Stundenportal-Sitzungen ungültig. Auch beim **ersten** Login nach dem Update wird eine neue Sitzungs-Version angelegt. Mitarbeiter müssen sich nach der Modulaktualisierung ggf. erneut einloggen. Das E-Mail-Aktivierungsverfahren und die Registrierung bleiben erhalten.

## Bestehende Funktionen

- Öffentliche Registrierung über die beim Mitarbeiter gespeicherte Arbeits-E-Mail.
- Bestätigung per E-Mail und Passwort-vergessen-Funktion.
- Monatliche Anwesenheitsübersicht mit Tagessummen aus `hr.attendance`, ohne Editiermöglichkeit.
- Zeitzone per Systemparameter `gl_employee_hours_portal.timezone` (Standard Europe/Berlin).

Öffentliche Seiten: `/mitarbeiter/stunden`, `/mitarbeiter/stunden/login`, `/mitarbeiter/stunden/registrieren`, `/mitarbeiter/stunden/passwort-vergessen`.

## Installation / Aktualisierung in Odoo.sh

1. Bestehenden Ordner `gl_employee_hours_portal` im Custom-Addons-Repository **durch den Ordner aus diesem ZIP ersetzen** (keine zweite Kopie mit anderem technischen Namen anlegen).
2. Commit und Push auf den Odoo.sh-Branch, zunächst Staging.
3. **Apps-Liste aktualisieren** und beim bestehenden Modul auf **Aktualisieren** klicken.
4. Unter **Einstellungen → Benutzer** einem gewünschten normalen internen Odoo-Nutzer die neue Gruppe *Mitarbeiter-Zugänge verwalten* zuweisen. HR-Manager und Systemadministratoren benötigen sie nicht zusätzlich.
5. Unter **Stundenportal → Mitarbeiter-Konten** einen Portal-Link und eine Passwortänderung testen.

Eine Passwortänderung betrifft nur das Stundenportal, **nicht das Odoo-Benutzerpasswort**. Bereits bestehende Konten und Stunden werden nicht migriert oder gelöscht.


## Korrektur Zeitzone München (v19.0.1.1.1)

Der Zeitzonen-Fix aus v19.0.1.0.4 wurde **in v19.0.1.1.0 integriert**.
Die Passwortverwaltung (Login-Links, individuelles Passwortsetzen, Generieren
neuer Passwörter, Reset-Mails, Rollen/Rechte und Sitzungsinvalidierung)
bleibt unverändert erhalten. Die Version v19.0.1.0.4 **nicht** als Basis
für diese Aktualisierung verwenden.

- Feste Zeitzone: `Europe/Berlin` (München), unabhängig von Odoo-User,
  Website-Besucher, Server oder der Firmen-Zeitzone. Die bisherige
  Parametereinstellung bleibt aus Kompatibilitätsgründen bestehen,
  beeinflusst die Stundenanzeige aber nicht mehr.
- Odoo-Anwesenheitszeiten aus `hr.attendance` werden als **UTC-Zeitstempel**
  gelesen und erst für die Darstellung nach München umgerechnet.
- Monatsgrenzen werden separat für MEZ/MESZ berechnet: UTC+1 (Winter)
  und UTC+2 (Sommer), einschließlich Ende März und Ende Oktober.
- Stunden zwischen lokaler Mitternacht werden in UTC auf Tagesabschnitte
  verteilt. Dadurch stimmt die gearbeitete Dauer auch am 23- bzw.
  25-Stunden-Tag der Zeitumstellung.
- Zeiträume, die eine Zeitumstellung überspannen, werden an den Uhrzeiten
  mit MEZ/MESZ gekennzeichnet.
- Alle bestehenden Anwesenheitsdatensätze bleiben **unverändert**.

### Überprüfung

Die reinen Zeitzonen- und Dauerberechnungen lassen sich ohne Odoo prüfen:

```
python -m unittest discover -s tests -p 'test_*.py' -v
```

Beispiele: Januar 08:00 UTC → 09:00 MEZ; Juli 08:00 UTC → 10:00 MESZ.
Während der Umstellung am 29.03.2026 bedeutet 01:30 MEZ bis 03:30 MESZ
nur 1 Stunde Echtzeit. Während der Umstellung am 25.10.2026 bedeutet
02:30 MESZ bis 02:30 MEZ ebenfalls 1 Stunde Echtzeit.

Update: Den technischen Modulordner `gl_employee_hours_portal` der bisherigen
Installation ersetzen, die App auf Odoo.sh **aktualisieren** (nicht
entfernen/deinstallieren), vor dem Produktions-Update auf Staging testen.
