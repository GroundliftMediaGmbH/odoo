# Groundlift Bruttopreis Eingabe – Odoo 19
Version **19.0.1.5.0**

## Fix in v1.5.0: Bruttopreis bleibt exakt der eingegebene Centbetrag

Bis v1.4 war `gross_list_price` ein berechnetes Feld (`compute` + `inverse`).
Dadurch entstand eine Rückkopplung:

1. Nutzer gibt z. B. 4,20 EUR brutto ein.
2. Modul berechnet daraus einen präzisen Nettopreis.
3. Weil `list_price` eine Abhängigkeit des Bruttopreis-Felds war, berechnete
   Odoo den Bruttopreis anschließend erneut aus Netto + Steuer.
4. Je nach Steuer-/Rundungskonfiguration konnte der Wert auf einen Nachbar-Cent
   springen.

Ab v1.5 ist der Bruttopreis ein **normal gespeicherter, führender Wert**.
4,20 EUR bleibt deshalb 4,20 EUR. Nur der Nettopreis wird daraus berechnet.

### Verhalten
- Eingabe 4,20 EUR -> gespeicherter Bruttopreis bleibt exakt 4,20 EUR.
- 19 % -> Nettopreis ca. 3,5294117647 EUR.
- 7 % -> Nettopreis ca. 3,9252336449 EUR.
- Änderung des Steuersatzes hält den Bruttopreis fest und berechnet Netto neu.
- Das bestehende POS-Präzisions-Patch aus v1.2/v1.4 bleibt erhalten.
- Keine Tax-/Summen-Patches aus der verworfenen v1.3 sind enthalten.

### Upgrade von v1.4
Beim Modul-Upgrade rekonstruiert ein Odoo-Upgrade-Skript den neuen gespeicherten
Bruttopreis aus den bestehenden präzisen Nettopreisen. Die bestehenden
Nettopreise werden während der Migration nicht verändert.

Bitte zuerst auf Staging aktualisieren und mit 4,19 / 4,20 / 4,21 testen.
