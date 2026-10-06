# Groundlift To-Do Categories – Odoo 19 SH

Version 19.0.1.5.0

## Neu in 1.5.0

### Hierarchische Kategorien
- Kategorien können eine **Überkategorie** besitzen.
- Beliebig verschachtelte Unterkategorien sind möglich.
- Links in der To-Do-Ansicht zeigt Odoos natives Search Panel die Kategorien hierarchisch als auf-/zuklappbaren Baum.
- Die Kategorie-Suche verwendet `child_of`, sodass eine Überkategorie inklusive ihrer Unterkategorien durchsucht/gefiltert werden kann.
- `Unkategorisiert` bleibt geschützt als Hauptkategorie und kann weder untergeordnet noch als Überkategorie verwendet werden.

### Hidden-To-Dos
- Neues Kontrollkästchen **Hidden** im To-Do-Formular und in der Schnellanlage.
- Hidden-To-Dos werden serverseitig per Record Rule geschützt, nicht nur in der Oberfläche ausgeblendet.
- Ein Hidden-To-Do ist nur für seine zugewiesenen Mitarbeiter sichtbar.
- Ist ein Hidden-To-Do unzugewiesen, ist es nur für seinen Ersteller sichtbar.
- Bei einem Upgrade wird auch die aus älteren Versionen stammende `noupdate`-Record-Rule automatisch korrigiert.

### Bestehende Funktionen bleiben erhalten
- `Unkategorisiert` für nicht zugewiesene/kategorielose To-Dos.
- Gemeinsame Phasen rechts im Board.
- Keine leere Phase/Spalte `Keine`.
- Meine To-Dos / Alle To-Dos.

## Update
Den bestehenden Ordner `gl_todo_categories` vollständig ersetzen, pushen und das Modul upgraden.
