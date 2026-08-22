# Sales & Layby Management System (`sales_manager_web`)

A lightweight, robust web-based retail management application built with **Flask** and **SQLite**. Designed specifically for retail operations, this system handles product cataloging, real-time inventory validation, customer profiles, instant cash sales, and multi-stage layby contract workflows.

---

## 🚀 Features

- **📦 Inventory & Stock Control**
  - Track product catalog with stock levels, retail pricing, and cost management.
  - Real-time inventory deduction and stock validation to prevent overselling.
  - Automated ID generation for all records.

- **👥 Customer Management**
  - Customer directory with instant search and transaction history tracking.
  - Link customer profiles directly to layby agreements and purchase orders.

- **🧾 POS & Sales Processing**
  - Log instant cash / card transactions with immediate inventory updates.
  - Record transaction details, quantities, and generate digital receipt summaries.

- **⏳ Layby Contract Lifecycle**
  - Dedicated layby workflow: partial deposits, flexible installment plans, and outstanding balance tracking.
  - Automated status updates upon contract completion or final fulfillment.

- **🔄 Data Architecture & Migration**
  - Relational SQLite database backend (`database.py`) ensuring ACID compliance and transaction safety.
  - Built-in migration pipeline (`migrate.py`) to migrate legacy CSV flat-file datasets directly into SQLite.

---

## 🛠️ Tech Stack

- **Backend:** Python, Flask
- **Database:** SQLite3
- **Frontend:** HTML5, CSS3, JavaScript (Jinja2 Templates)
- **Data Layer & Tooling:** Python Standard Library (`sqlite3`, `csv`, `pathlib`)

---

## 📂 Project Structure

```text
sales_manager_web/
│
├── static/              # Custom stylesheets and client-side JavaScript
├── templates/           # Jinja2 HTML templates (Dashboard, Sales, Layby, Inventory)
├── .gitignore           # Git ignore rules for database files and environments
├── app.py               # Main Flask application and routing logic
├── database.py          # Database connection, schemas, and query helpers
├── migrate.py           # Data migration utility (CSV to SQLite)
├── requirements.txt     # Python project dependencies
└── README.md            # Project documentation
