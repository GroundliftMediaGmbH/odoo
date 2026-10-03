# Groundlift Bruttopreis Eingabe – Odoo 19

Dieses Modul ergänzt Produkte um ein editierbares Feld **Bruttopreis**.

## Verhalten

- Im Feld **Bruttopreis** wird z. B. `5,80 €` eingegeben.
- Odoo berechnet daraus anhand der hinterlegten Verkaufssteuer automatisch den
  präzisen Nettopreis und schreibt ihn in das Standardfeld **Verkaufspreis**.
- Bei 19 % Verkaufssteuer werden aus `5,80 €` intern ca. `4,87394958 €` netto.
- Der Nettopreis wird bewusst **nicht auf zwei Nachkommastellen gerundet**.
  Dadurch bleiben Summen bei mehreren Stück sauber.
- Wird ein Produkt ohne Verkaufssteuer verwendet, sind Brutto- und Nettopreis identisch.
- Das Modul verwendet für die Rückrechnung die native Odoo-19-Methode
  `product.template._get_list_price()`.

## Installation

1. Modulordner `gl_gross_sales_price` in das Custom-Addons-/GitHub-Repository legen.
2. Auf Odoo.sh committen und deployen.
3. Apps-Liste aktualisieren.
4. Nach **Groundlift Bruttopreis Eingabe** suchen und installieren.

Das Feld erscheint direkt unter dem Standard-Verkaufspreis im Produktformular.
