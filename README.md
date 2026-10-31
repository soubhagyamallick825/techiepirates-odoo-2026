# Brightloop Subscription Management System

One system for plans, subscriptions, recurring billing, payments and revenue reporting, built for the Odoo Hackathon problem "Brightloop Software". It replaces spreadsheets, hand-typed invoices and bank-statement matching with a single billing backbone.

## What it does

| Module | Included |
|---|---|
| Auth and roles | Customer self-signup (one account per email), password rule (9+ characters, upper, lower, special), forgot-password flow with a simulated email inbox, three roles (Admin, Internal Staff, Customer portal), only Admin can add staff |
| Products and plans | Products with type, sales price, cost price and notes; variants with price extra (for example Brand = Odoo adds 560); plans with billing frequency, minimum quantity, availability dates and per-plan switches for auto-close, early close, pause and renew |
| Quotations and subscriptions | Quotation templates, auto-numbered subscriptions (`SUB-2026-0001`), status ribbon Draft > Quotation > Confirmed > Active > Closed (plus Paused), action buttons shown only when the plan allows them, customer add-on switching |
| Tax and discounts | Admin-defined tax rules applied to every invoice; admin-only discount rules (fixed or percentage, minimum amount or quantity, start and end dates, max uses) for products or whole subscriptions, applied automatically on the next invoice |
| Billing day | One click generates invoices for all due subscriptions with customer, lines, tax and discounts filled in. A unique `(subscription, period start, period end)` constraint guarantees nothing is billed twice |
| Invoices and payments | Draft > Confirmed > Paid (or Cancelled), confirm, cancel, send email (logged to the inbox), print or save as PDF, partial and full payments by Bank Transfer, UPI, Card or Cash, automatic Overdue flag |
| Finance dashboard | Active subscriptions, MRR, ARR, revenue collected, receivables, overdue count, charts, filters by date, plan, frequency and invoice status, and the query time shown in the footer |

## Tech stack

- Backend: Python 3, Flask, SQLite (`sqlite3`)
- Frontend: single HTML page with Tailwind CSS, Chart.js and Lucide icons (loaded from CDNs, so internet access is needed)
- Indexes: `subscription(status, next_billing)`, `invoice(status, due_date)`, plus customer and line indexes. All lists use server-side pagination (25 rows per page)

## Run it

```bash
git clone https://github.com/soubhagyamallick825/techiepirates-odoo-2026.git
cd techiepirates-odoo-2026
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
python -m pip install flask
python app.py
```

Open http://localhost:5000. The first start creates `brightloop.db` and seeds demo data (products, plans, taxes, discounts, templates, sample subscriptions, overdue invoices and 500 bulk subscriptions). To reset everything, stop the server, delete `brightloop.db` and start again.

If port 5000 is busy (common on Mac), change the last line of `app.py` to `app.run(port=5001)`.

## Demo logins

Password for all demo users: `Demo@12345`

| Role | Email |
|---|---|
| Admin | admin@brightloop.com |
| Internal Staff | staff@brightloop.com |
| Customer | customer@brightloop.com |

The dark bar at the top of the page also has one-click role switching, **Trigger Billing Day**, **Seed 2,000 Subscriptions** and the **Email inbox**.

## 3-minute demo script

1. **Dashboard.** Click Admin. Point out the KPI cards, the charts, the filters and the query time in the footer.
2. **Quotation to subscription.** Open Subscriptions, click New subscription, pick the template "Enterprise Offer (Odoo)", create it. The product unit price is 1,560 (1,000 base plus 560 for the Odoo variant). Walk it along the ribbon: Send quotation, Confirm, Activate.
3. **Billing day.** Click Trigger Billing Day. The toast reports how many invoices were generated, how many already-billed subscriptions were skipped and how many discounts were applied. Click it again and nothing is billed twice.
4. **Invoice and payment.** Open Invoices, open a Draft invoice, Confirm it, record a partial payment, then pay the balance and watch it turn Paid. Open Print / download PDF. Filter by Overdue to see invoices to chase.
5. **Plan rules.** Open an Enterprise Yearly subscription: Pause and Close early are not offered. Open a Business Monthly one: they are.
6. **Customer portal.** Click Customer portal. Only that customer's subscriptions and invoices are visible. Switch an add-on on or off.
7. **Accounts.** Log out, try signing up with a weak password (rejected), then use Forgot password and open the reset link from the Email inbox.
8. **Scale.** Click Seed 2,000 Subscriptions, then browse Subscriptions, Invoices and the Dashboard and watch the query time stay well under 2 seconds.

## Project structure

```
app.py              Flask API, billing engine, seeder
static/index.html   Single-page interface
```

## Notes and limitations

- Catalog items (products, plans, taxes, discounts, templates) can be created but not yet edited or deleted.
- Invoices are built from subscription product lines. The plan's base cost is stored and shown but is not added as a separate invoice line.
- Emails (password reset, invoice send) are simulated in the in-app inbox, not sent over SMTP.
- The secret key in `app.py` is a demo value. Change it before any real deployment.
