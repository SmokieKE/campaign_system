
# Constituency SMS Web Application

A full-stack bulk SMS dashboard for constituency offices that need to send messages to members efficiently instead of texting people one by one. The system includes a structured contacts database, campaign management, delivery tracking, and TalkSasa API gateway integration. Built with Flask, Python, JavaScript, and linked to a native MariaDB/MySQL database via phpMyAdmin.

---

## Project Structure

```text
Bulk-sms-system-main/
|-- app.py              # Flask backend, DB models, background threading + REST API
|-- requirements.txt    # Python dependencies (Flask, SQLAlchemy, PyMySQL, etc.)
|-- README.md           # Documentation and setup guide
|-- .gitignore          # Keeps build tracking (venv, caching) out of git commits
|-- static/
    |-- index.html      # Single-page frontend dashboard layout (HTML, Tailwind, JS)

```

The application uses **MariaDB/MySQL** managed via **phpMyAdmin** as its main permanent persistence database management layer.

---

## Setup

### 1. Install Dependencies

Ensure your Python virtual environment (`venv`) is activated, then run:

```bash
pip install -r requirements.txt
pip install pymysql

```

### 2. Configure Your Database Engine (phpMyAdmin)

Ensure your native system engine microservices are live and active on your system:

```bash
sudo systemctl start mariadb
sudo systemctl start apache2

```

1. Open your browser and navigate directly to: `http://localhost/phpmyadmin`
2. Authenticate using your custom administrative account (e.g., username: `enter username` / password: `enter password`).
3. Click on the **Databases** tab, type **`sms_app_db`** into the box field, and click **Create**.

### 3. Set Gateway Credentials

Open **`app.py`** and ensure your local configurations point to your newly provisioned user:

```python
MYSQL_USER = "enter username"
MYSQL_PASS = "enter password"
MYSQL_HOST = "localhost"
MYSQL_DB   = "sms_app_db"

# TalkSasa REST API Gateway settings
TALKSASA_SENDER_ID = "YOUR_SENDER_ID"
TALKSASA_API_KEY = "YOUR_API_KEY_HERE"

```

### 4. Run the Application

Start up your local Flask server instance:

```bash
python3 app.py

```

Open **`http://localhost:8080`** (or the port logged in your console environment output) to manage your system dashboard!

---

## Features

### Contacts Management

* Add custom contacts directly using the interactive frontend entry form.
* Import data models securely without automated schema overrides.
* Persistent persistence storage mapping—contacts do not disappear on refresh.
* Deep profile records tracking metrics like: National ID, Ward, Sublocation, Village, Farm Allocation, Gender, and Age Group fields.

### Campaigns & Broadcast Engines

* Queue campaigns asynchronously without locking up main thread operations.
* Dynamic delivery log status aggregation.
* Customized payload formatting delivering individual routing strings directly to the API endpoint loop handlers.

---

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/stats` | Fetches aggregated summary stats |
| GET | `/api/contacts` | Lists all active contacts |
| POST | `/api/contacts` | Adds a single new contact record |
| DELETE | `/api/contacts/<id>` | Removes a contact completely |
| GET | `/api/campaigns` | Lists complete campaign histories |
| POST | `/api/campaigns` | Dispatches new campaign tracking instances |
| GET | `/api/campaigns/<id>` | Fetches sub-logs matching target campaign ID |

---
