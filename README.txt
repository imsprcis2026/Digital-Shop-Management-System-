DIGITAL SHOP MANAGEMENT SYSTEM (DSMS)
======================================

Technology
----------
- Python
- Flask
- SQLite
- HTML
- CSS
- JavaScript

PROJECT FILES
-------------
app.py
    Main Flask application. Contains routes, database operations,
    authentication, stock, sales, payments and reports.

templates/base.html
    Common header, hamburger menu and Settings section.

templates/index.html
    Dashboard with the four main summary cards and quick actions.

templates/profile.html
    Account opening screen and logged-in user profile.

templates/auth.html
    Login and create-account forms.

templates/table.html
    Stock, sales, payment, pending-payment and purchase tables.
    Each row uses a clean three-dots action menu.

templates/form.html
    Add and edit forms for stock and sales.

templates/bill.html
    Bill display. Bills remain in English.

templates/print.html
    Printable report layout.

templates/report.html
    Stock and sales reports.

templates/customer.html
    Customer history.

templates/pay.html
    Pending payment screen.

templates/return.html
    Sale return screen.

templates/profile_edit.html
    Edit shop details.

static/style.css
    Complete application styling, responsive layout and dashboard design.

static/script.js
    Menu controls, row action menus, sale calculations, device time,
    form helpers and interface language handling.

requirements.txt
    Python packages required to run the project.

HOW TO RUN
----------
1. Install dependencies:
   pip install -r requirements.txt

2. Start the application:
   python app.py

3. Open in the browser:
   http://127.0.0.1:5000

IMPORTANT BEHAVIOUR
-------------------
- The Account screen opens first.
- Pressing Back on the Account screen opens the Dashboard.
- Language selection is available only inside Menu > Settings.
- The selected language is saved for the interface.
- Bills and printable bills stay in English.
- Table actions are hidden inside the three-dots menu.
- Existing features and data behaviour are kept unchanged.
