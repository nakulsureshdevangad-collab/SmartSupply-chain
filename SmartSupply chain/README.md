# SmartSupply

Smart Procurement & Supply Chain Management System built with Flask, SQLite, HTML, CSS, and JavaScript.

## Run locally

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. Install the app dependencies and start the app:

   ```powershell
   pip install -r requirements.txt
   py app.py
   ```

3. Open http://127.0.0.1:5000. The SQLite database and sample records are created automatically on the first run.

## Enable AI chat

AI restock suggestions work from the app's stock, reorder levels, and incoming purchase orders. To enable the conversational assistant:

1. Create an OpenAI API key in your OpenAI developer account.
2. Copy `.env.example` to `.env` and replace the placeholder with your key:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

3. Restart the app. Keep `.env` private; it is excluded from Git.

When you use AI chat, SmartSupply sends your question and a limited summary of product stock, purchase orders, and delivery statuses to the OpenAI API. It excludes supplier contact names and email addresses. Chat is read-only; it cannot create or modify orders.

## Included workflows

- Maintain supplier contacts and product associations.
- Track stock quantities, unit costs, and reorder thresholds.
- Create purchase orders and update their status.
- Add shipment tracking and update delivery progress.
- Review purchase spend, supplier activity, and inventory reports.
- Review restock suggestions and ask the AI assistant questions about current operations.

This is a local project starter. Authentication, role permissions, production deployment settings, durable demand forecasting, and supplier price quote history are not included.
