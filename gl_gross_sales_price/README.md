# Groundlift Bruttopreis Eingabe – Odoo 19

Version **19.0.1.2.0**

## Was v1.2 korrigiert

Die frühere Version verwendete Odoos `product.template._get_list_price()`.
Diese Methode ruft `account.tax.compute_all()` mit der normalen
Währungsrundung auf. Deshalb wurde bei 19 % aus 3,80 EUR bereits serverseitig
3,19 EUR statt 3,193277310924... EUR.

v1.2 verwendet für die Rückrechnung:

- `force_price_include=True`
- `round_base=False`

Damit bleibt der steuerfreie Basispreis intern exakt.

Zusätzlich kennzeichnet das Modul Produkte, deren Preis über das Feld
**Bruttopreis** gepflegt wird. Nur bei diesen Produkten unterbindet der
POS-Patch die zusätzliche Rundung von `price_unit` auf die Product-Price-
Dezimalstellen.

## Wichtig nach Upgrade von v1.0/v1.1

Bestehende Produkte wurden bereits mit dem alten gerundeten Nettopreis
gespeichert. Sie müssen einmal korrigiert werden.

Einzelprodukt:
- Produkt öffnen
- **Netto exakt neu berechnen** klicken

Mehrere Produkte:
- Produktliste öffnen
- betroffene Produkte markieren
- Aktion **Bruttopreis → exakten Nettopreis anwenden**

Danach POS komplett schließen und neu öffnen.

Beispiel:
- Bruttopreis 3,80 EUR
- exakter Netto-Basispreis 3,193277310924...
- zwei Produkte zu je 3,80 EUR = 7,60 EUR
