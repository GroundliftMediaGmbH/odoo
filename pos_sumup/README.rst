POS SumUp Integration
=====================

Integrate your Odoo Point of Sale with SumUp Solo payment terminals.

Features
--------
*   **Direct Integration**: Connect securely to SumUp terminals directly from the Odoo POS interface.
*   **Payment Processing**: Fast and reliable card payments.
*   **Tipping**: Support for tipping on the terminal (configurable rates).
*   **Multiple Terminals**: Manage multiple terminals per shop or payment method.

Configuration
-------------
1.  **Credentials**:
    *   Go to **Invoicing > Configuration > Payment Providers**.
    *   Create or edit the "SumUp" provider.
    *   Enter your **Merchant Code** and **API Key** (generated from the SumUp Developer Dashboard).
    *   Set the state to **Enabled**.

2.  **Payment Method**:
    *   Go to **Point of Sale > Configuration > Payment Methods**.
    *   Create a new payment method (e.g., "Card").
    *   Check **Use a Payment Terminal** and select **SumUp**.
    *   **Pair Reader**: Click "Pair New Reader" or select an existing one. Enter the pairing code displayed on your SumUp device.
    *   **Tipping**: Enable "Enable Tipping" and set "Tip Rates" (e.g., `10,15,20`) if desired.

Usage
-----
1.  Open the POS Session.
2.  Select the **Card** payment method when processing an order.
3.  The amount will be pushed to the terminal.
4.  Customer taps/inserts card.
5.  Upon success, the payment is automatically validated in Odoo.