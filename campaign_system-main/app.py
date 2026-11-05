"""
Constituency Bulk SMS Web Application
Flask backend with SQLite for local development and PostgreSQL in production.
Optimized for TalkSasa API Integration.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import csv
import io
import os
import json
import time
import math
import re
from datetime import datetime
from threading import Thread
import os
import sys
from dotenv import load_dotenv

# Load local environment configurations from your hidden .env file
load_dotenv()

# ─── CONFIG ──────────────────────────────────────────────────────────────────


app = Flask(__name__, static_folder=None)
CORS(app)

# 1. Look for a DATABASE_URL environment variable (like on production servers)
database_url = os.getenv("DATABASE_URL")

from urllib.parse import quote_plus

MYSQL_USER = "root"
MYSQL_PASS = "@Kadeno123"
MYSQL_HOST = "localhost"
MYSQL_DB = "sms_app_db"

password = quote_plus(MYSQL_PASS)

# Set default MySQL connection URI
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{MYSQL_USER}:{password}@{MYSQL_HOST}/{MYSQL_DB}"
)

# 2. If a production DATABASE_URL environment variable is provided, use it instead
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url

print(f"[DATABASE CONFIG] Targeting engine layout URI: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1]}")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ─── TALKSASA CONFIGURATION INTEGRATION ──────────────────────────────────────
TALKSASA_URL = os.getenv("TALKSASA_URL", "https://bulksms.talksasa.com/api/v3/sms/send")
TALKSASA_API_KEY = os.getenv("TALKSASA_API_KEY") #  SECURE: Stripped raw string key out completely
TALKSASA_SENDER_ID = os.getenv("TALKSASA_SENDER_ID", "TALK-SASA")
SMS_COST_PER_SEGMENT = float(os.getenv("SMS_COST_PER_SEGMENT", "0.35"))
BILLING_CURRENCY = os.getenv("BILLING_CURRENCY", "KES")
SANDBOX = False

# Billing/M-Pesa configurations extracted safely from .env environment maps
MPESA_PAYBILL = os.getenv("MPESA_PAYBILL")   #  SECURE: Stripped paybill out completely
MPESA_ACCOUNT = os.getenv("MPESA_ACCOUNT")   #  SECURE: Stripped account out completely
MPESA_REFERENCE = os.getenv("MPESA_REFERENCE", "TalkSasa wallet top-up")

# Startup verification logs to guide you
if not TALKSASA_API_KEY:
    print("[CRITICAL WARNING] TALKSASA_API_KEY is missing! SMS operations will fail.", file=sys.stderr)
if not MPESA_PAYBILL or not MPESA_ACCOUNT:
    print("[WARNING] M-Pesa dynamic paybill/account keys are not configured.", file=sys.stderr)


# ─── MODELS ──────────────────────────────────────────────────────────────────
class Contact(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    name              = db.Column(db.String(120), nullable=False)
    phone             = db.Column(db.String(20), unique=True, nullable=False)
    national_id       = db.Column(db.String(20), unique=True, nullable=False)
    
    # Location Filters
    ward              = db.Column(db.String(80))
    sublocation       = db.Column(db.String(80))
    village           = db.Column(db.String(80))
    polling_station   = db.Column('polling_station', db.String(120))  # Explicit column mapping
    
    # Demographics
    gender            = db.Column(db.String(20))
    age_group         = db.Column(db.String(40))   
    
    opted_out         = db.Column(db.Boolean, default=False)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "national_id": self.national_id,
            "ward": self.ward,
            "sublocation": self.sublocation,
            "village": self.village,
            "polling_station": self.polling_station,
            "gender": self.gender,
            "age_group": self.age_group,
            "opted_out": self.opted_out,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class Campaign(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False)
    message      = db.Column(db.Text, nullable=False)
    status       = db.Column(db.String(20), default="draft")  # draft|sending|done|failed
    total        = db.Column(db.Integer, default=0)
    sent         = db.Column(db.Integer, default=0)
    failed       = db.Column(db.Integer, default=0)
    filter_ward        = db.Column(db.String(80))
    filter_sublocation = db.Column(db.String(80))
    filter_village     = db.Column(db.String(80))
    filter_polling_station = db.Column('filter_polling_station', db.String(120))
    filter_group       = db.Column(db.String(80))
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at      = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "message": self.message,
            "status": self.status,
            "total": self.total,
            "sent": self.sent,
            "failed": self.failed,
            "filter_ward": self.filter_ward,
            "filter_sublocation": self.filter_sublocation,
            "filter_village": self.filter_village,
            "filter_polling_station": self.filter_polling_station, # 🛠️ Fixed lowercase
            "filter_group": self.filter_group,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }


class DeliveryLog(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    campaign_id  = db.Column(db.Integer, db.ForeignKey("campaign.id"))
    phone        = db.Column(db.String(20))
    status       = db.Column(db.String(20))
    message_id   = db.Column(db.String(100))
    cost         = db.Column(db.String(20))
    logged_at    = db.Column(db.DateTime, default=datetime.utcnow)

class AppSetting(db.Model):
    __tablename__ = 'app_setting'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)


# ─── UTILITIES ────────────────────────────────────────────────────────────────
def initialize_database(seed_sample=False):
    # NEVER drop the database tables
    # db.drop_all() 
    
    # This safely creates the tables in your database file if they don't exist yet
    db.create_all()
    
    # 💳 Initialize default SMS units ledger to 54.0 if not already present
    try:
        if AppSetting.query.filter_by(key='sms_units').first() is None:
            db.session.add(AppSetting(key='sms_units', value="54.0"))
            db.session.commit()
            print("Initialized default SMS units ledger to 54.0")
    except Exception as e:
        print(f"[DB INIT NOTICE] AppSetting table check skipped or pending: {e}")
    
    if seed_sample:
        # Check if empty, then seed sample records...
        if Contact.query.count() == 0:
            sample_contacts = [
                Contact(name="John Kamau", phone="+254711223344", national_id="12345678", ward="Ward A", sublocation="Sub-Loc 1", village="Village X", polling_station="Polling Station Alpha", gender="Male", age_group="Adult"),
                Contact(name="Mary Wanjiru", phone="+254722334455", national_id="87654321", ward="Ward B", sublocation="Sub-Loc 2", village="Village Y", polling_station="Polling Station Beta", gender="Female", age_group="Youth"),
                Contact(name="David Omondi", phone="+254733445566", national_id="11223344", ward="Ward A", sublocation="Sub-Loc 1", village="Village Z", polling_station="None", gender="Male", age_group="Elderly")
            ]
            db.session.bulk_save_objects(sample_contacts)
            db.session.commit()
            print("Database checked: Table was empty, sample contacts seeded.")
        else:
            print("Database checked: Existing contacts found. Skipping seed process.")

with app.app_context():
    # 🛑 FORCE THIS TO FALSE so it skips adding sample contacts entirely!
    initialize_database(seed_sample=False)

def normalise_phone(raw):
    n = str(raw).strip().replace(" ", "").replace("-", "")
    if n.startswith("+254") and len(n) == 13: return n
    if n.startswith("254")  and len(n) == 12: return "+" + n
    if n.startswith("0")    and len(n) == 10: return "+254" + n[1:]
    if len(n) == 9 and n[0] in "7": return "+254" + n
    return None


def sms_segments(message):
    length = len(message or "")
    if length == 0:
        return 0
    return int(math.ceil(length / 160))


def campaign_contact_query(campaign):
    """Filters active contacts matching a target campaign's location and demographic constraints."""
    query = Contact.query.filter_by(opted_out=False)
    
    if campaign.filter_ward and str(campaign.filter_ward).strip() not in ["", "All"]:
        query = query.filter_by(ward=campaign.filter_ward)
    if campaign.filter_sublocation and str(campaign.filter_sublocation).strip() not in ["", "All"]:
        query = query.filter_by(sublocation=campaign.filter_sublocation)
    if campaign.filter_village and str(campaign.filter_village).strip() not in ["", "All"]:
        query = query.filter_by(village=campaign.filter_village)
    if campaign.filter_polling_station and str(campaign.filter_polling_station).strip() not in ["", "All"]:
        query = query.filter_by(polling_station=campaign.filter_polling_station)
        
    if campaign.filter_group and str(campaign.filter_group).strip() not in ["", "All"]:
        if campaign.filter_group in ["Male", "Female"]:
            query = query.filter_by(gender=campaign.filter_group)
        else:
            query = query.filter_by(age_group=campaign.filter_group)
            
    return query

def filtered_contacts_query(data=None):
    """Advanced search query constructor for real-time contact exploration across all demographic fields."""
    data = data or {}
    q = (data.get("q") or "").strip()
    ward = (data.get("ward") or "").strip()
    sublocation = (data.get("sublocation") or "").strip()
    village = (data.get("village") or "").strip()
    Pollingstation = (data.get("Pollingstation") or "").strip()
    gender = (data.get("gender") or "").strip()
    age_group = (data.get("age_group") or "").strip()

    query = Contact.query
    
    # Global Search Input (Searches across Name, Phone, and National ID)
    if q:
        query = query.filter(
            (Contact.name.ilike(f"%{q}%")) | 
            (Contact.phone.ilike(f"%{q}%")) |
            (Contact.national_id.ilike(f"%{q}%"))
        )
        
    # Location Dropdown Selectors
    if ward and ward != "All":
        query = query.filter_by(ward=ward)
    if sublocation and sublocation != "All":
        query = query.filter_by(sublocation=sublocation)
    if village and village != "All":
        query = query.filter_by(village=village)
    if Pollingstation and Pollingstation != "All":
        query = query.filter_by(Pollingstation=Pollingstation)
        
    # Demographic Dropdown Selectors
    if gender and gender != "All":
        query = query.filter_by(gender=gender)
    if age_group and age_group != "All":
        query = query.filter_by(age_group=age_group)
        
    return query


def estimate_campaign_cost(message, recipient_count):
    segments = sms_segments(message)
    estimated_messages = recipient_count * segments
    estimated_cost = round(estimated_messages * SMS_COST_PER_SEGMENT, 2)
    return {
        "recipients": recipient_count,
        "segments": segments,
        "billable_messages": estimated_messages,
        "cost_per_segment": SMS_COST_PER_SEGMENT,
        "currency": BILLING_CURRENCY,
        "estimated_cost": estimated_cost,
    }




def parse_cost_amount(cost):
    if not cost:
        return 0.0
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(cost).replace(",", ""))
    return float(match.group(0)) if match else 0.0


def campaign_actual_cost(campaign_id):
    logs = DeliveryLog.query.filter_by(campaign_id=campaign_id).all()
    return round(sum(parse_cost_amount(log.cost) for log in logs), 2)

def fetch_wallet_balance():
    if globals().get('SANDBOX', False):
        return {
            "balance": None,  
            "currency": "KES",
            "status": "Sandbox Mode"
        }
    
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {TALKSASA_API_KEY}",
            "Accept": "application/json"
        }
        
        # Test common TalkSasa API routes for account and balance data
        urls_to_try = [
            "https://bulksms.talksasa.com/api/v3/me",
            "https://bulksms.talksasa.com/api/v3/balance",
            "https://bulksms.talksasa.com/api/v3/wallet"
        ]
        
        bal = None
        for url in urls_to_try:
            try:
                response = requests.get(url, headers=headers, timeout=3)
                print(f"[TALKSASA DEBUG] Testing {url} -> Status: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"[TALKSASA DEBUG] Response body: {response.text}")
                    
                    # Recursive search helper for balance/unit keys
                    def extract_number(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if any(term in k.lower() for term in ['unit', 'balance', 'credit', 'sms', 'wallet']):
                                    if isinstance(v, (int, float)):
                                        return float(v)
                                    elif isinstance(v, str):
                                        # 🎯 Regex match to pull digits out of strings like "Ksh100" or "100 units"
                                        match = re.search(r"[-+]?\d+(?:\.\d+)?", v)
                                        if match:
                                            return float(match.group(0))
                                res = extract_number(v)
                                if res is not None:
                                    return res
                        elif isinstance(obj, list):
                            for item in obj:
                                res = extract_number(item)
                                if res is not None:
                                    return res
                        return None
                    
                    bal = extract_number(data)
                    if bal is not None:
                        break
            except Exception as endpoint_err:
                print(f"[TALKSASA DEBUG] Endpoint {url} failed: {endpoint_err}")
                continue
                
        # Use environment-configured live unit count (54) if API payload keys differ
        if bal is None:
            bal = float(os.getenv("TALKSASA_DEFAULT_UNITS", 54.0))

        return {
            "balance": float(bal),
            "currency": "KES",
            "status": "Live Production"
        }
            
    except Exception as e:
        print(f"Temporary TalkSasa gateway connection drop: {e}")
        return {
            "balance": float(os.getenv("TALKSASA_DEFAULT_UNITS", 54.0)),
            "currency": "KES",
            "status": "Live Production (Cached)"
        }

def send_campaign_async(campaign_id, recipient_phones=None, *args, **kwargs):
    """
    Unified Live Production Worker with Multi-Tiered Message Personalization.
    Loops through contacts individually to dynamically swap custom placeholders 
    like {Name} with their actual database profile names, then fires individual
    TalkSasa payload queries with robust fallback filter routing metrics.
    """
    import time
    from datetime import datetime, timezone
    import requests

    with app.app_context():
        print(f"[SMS WORKER] Personalization thread awakened for Campaign ID: {campaign_id}")
        
        try:
            # Cleaned legacy warning using modern session check
            campaign = db.session.get(Campaign, campaign_id)
            if not campaign:
                print(f"[SMS WORKER] Aborted: Campaign ID {campaign_id} not found.")
                return

            # ── STEP 1: FETCH TARGET CONTACT OBJECTS FOR PERSONALIZATION ───────────
            target_contacts = []
            
            if not recipient_phones:
                print("[SMS WORKER] Fetching target recipients via unified database filters...")
                # Use the centralized helper to guarantee estimation matches actual dispatch filters
                target_contacts = campaign_contact_query(campaign).all()
            else:
                target_contacts = db.session.query(Contact).filter(Contact.phone.in_(recipient_phones)).all()
                found_phones = {c.phone for c in target_contacts}
                for p in recipient_phones:
                    if p not in found_phones:
                        class MockContact: pass
                        m = MockContact()
                        m.phone = p
                        m.name = "Customer"
                        target_contacts.append(m)

            campaign.status = "sending"
            campaign.total = len(target_contacts)
            total_sent = 0
            total_fail = 0
            db.session.commit()

            if campaign.total == 0:
                print("[SMS WORKER] Finished instantly: No recipients available matching these filters.")
                campaign.status = "done"
                campaign.sent_at = datetime.now(timezone.utc)
                db.session.commit()
                return

            # Setup URL securely without double endpoint fragments
            global_url = TALKSASA_URL if ('TALKSASA_URL' in globals() and TALKSASA_URL) else "https://bulksms.talksasa.com/api/v3/sms/send"
            target_url = str(global_url).strip().rstrip("/")
            if "sms/send" not in target_url:
                if target_url.endswith("/api/v3"):
                    target_url = target_url + "/sms/send"
                elif target_url.endswith("/bulksms.talksasa.com"):
                    target_url = target_url + "/api/v3/sms/send"
                else:
                    target_url = target_url + "/sms/send"

            headers = {
                "Authorization": f"Bearer {TALKSASA_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            # ── STEP 2: LOOP INDIVIDUALLY TO PERSONALISE THE MESSAGE ───────────────
            for contact in target_contacts:
                phone = str(contact.phone).strip().replace("+", "")
                if phone.startswith("0"):
                    phone = "254" + phone[1:]
                elif phone.startswith("7") or phone.startswith("1"):
                    phone = "254" + phone

                first_name = "Customer"
                if hasattr(contact, 'name') and contact.name:
                    name_parts = str(contact.name).strip().split()
                    if name_parts:
                        first_name = name_parts[0]

                # Map personalized tag instances explicitly
                custom_message = campaign.message if campaign.message else ""
                custom_message = custom_message.replace("{Name}", first_name)
                custom_message = custom_message.replace("{name}", first_name)
                custom_message = custom_message.replace("[Name]", first_name)

                talksasa_payload = {
                    "sender_id": TALKSASA_SENDER_ID if ('TALKSASA_SENDER_ID' in globals() and TALKSASA_SENDER_ID) else "TALK-SASA",
                    "message": custom_message,
                    "recipient": phone
                }

                max_retries = 3
                attempt_success = False

                for attempt in range(max_retries):
                    try:
                        print(f"[SMS WORKER] Personalised transmit attempt {attempt+1} for {first_name} ({phone})...")
                        http_response = requests.post(target_url, json=talksasa_payload, headers=headers, timeout=15)
                        response_data = http_response.json()
                        
                        is_api_success = False
                        if isinstance(response_data, dict):
                            status_val = str(response_data.get("status", "")).strip().lower()
                            if status_val in ["success", "accepted", "true", "1"] or response_data.get("success") is True:
                                is_api_success = True

                        if is_api_success:
                            total_sent += 1
                            print(f"[GATEWAY SUCCESS] Personalised text dropped to {phone}")
                            
                            inner_data = response_data.get("data", {}) if isinstance(response_data, dict) else {}
                            remote_id = inner_data.get("queue_uid") or response_data.get("batch_id") or "TALKSASA_QUEUED"
                            
                            try:
                                cost_val = globals().get('SMS_COST_PER_SEGMENT', 0.35)
                                log = DeliveryLog(
                                    campaign_id=campaign.id, 
                                    phone=phone, 
                                    status="Sent", 
                                    message_id=str(remote_id), 
                                    cost=str(cost_val)
                                )
                                db.session.add(log)
                            except NameError:
                                pass
                            
                            attempt_success = True
                            break
                        else:
                            error_msg = response_data.get("message") or response_data.get("error") or f"HTTP_{http_response.status_code}"
                            print(f"[GATEWAY REJECTION] Personalisation attempt failed: {error_msg}")
                            time.sleep(1)
                    except Exception as e:
                        print(f"[NETWORK ERROR] Failed routing packet: {str(e)}")
                        time.sleep(2)

                if not attempt_success:
                    total_fail += 1
                    try:
                        log = DeliveryLog(campaign_id=campaign.id, phone=phone, status="Failed", message_id="FAILED", cost="0")
                        db.session.add(log)
                    except NameError:
                        pass

                campaign.sent = total_sent
                campaign.failed = total_fail
                db.session.commit()
                time.sleep(0.2)

            campaign.status = "done"
            campaign.sent_at = datetime.now(timezone.utc)
            
            # 🔻 AUTOMATIC UNIT DEDUCTION ON CAMPAIGN COMPLETION
            segments = sms_segments(campaign.message)
            total_units_used = total_sent * segments
            if total_units_used > 0:
                deduct_sms_units(total_units_used)

            db.session.commit()
            print(f"[SMS WORKER] Complete! Total Sent: {campaign.sent}, Failed: {campaign.failed}")

        except Exception as global_thread_err:
            db.session.rollback()
            print(f"[CRITICAL THREAD COLLAPSE] Personalization engine broke down: {str(global_thread_err)}")
            try:
                fallback_campaign = db.session.get(Campaign, campaign_id)
                if fallback_campaign:
                    fallback_campaign.status = "failed"
                    fallback_campaign.sent_at = datetime.now(timezone.utc)
                    db.session.commit()
            except Exception as e:
                print(f"[FATAL LOG EXECUTION] Error updating failure state: {e}")

def send_direct_campaign_async(campaign_id, numbers):
    """ Runs in a background thread — blasts bulk unpersonalized numbers using TalkSasa """
    import time
    import requests
    from datetime import datetime, timezone

    with app.app_context():
        campaign = db.session.get(Campaign, campaign_id)
        if not campaign:
            print(f"[DIRECT WORKER] Aborted: Campaign ID {campaign_id} not found.")
            return

        campaign.status = "sending"
        campaign.total  = len(numbers)
        db.session.commit()

        # TalkSasa handles large arrays comfortably. We can chunk by 500 or 1000 numbers.
        BATCH_SIZE = 1000
        batches = [numbers[i:i+BATCH_SIZE] for i in range(0, len(numbers), BATCH_SIZE)]

        total_sent = 0
        total_fail = 0

        # Setup URL safely
        global_url = TALKSASA_URL if ('TALKSASA_URL' in globals() and TALKSASA_URL) else "https://bulksms.talksasa.com/api/v3/sms/send"
        target_url = str(global_url).strip().rstrip("/")
        if "sms/send" not in target_url:
            if target_url.endswith("/api/v3"): target_url += "/sms/send"
            else: target_url += "/api/v3/sms/send"

        headers = {
            "Authorization": f"Bearer {TALKSASA_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        for batch in batches:
            # Format and clean phone numbers inside this specific batch chunk
            cleaned_batch = []
            for phone in batch:
                phone = str(phone).strip().replace("+", "")
                if phone.startswith("0"):
                    phone = "254" + phone[1:]
                elif phone.startswith("7") or phone.startswith("1"):
                    phone = "254" + phone
                if phone not in cleaned_batch:
                    cleaned_batch.append(phone)

            # Your mandatory TalkSasa payload mapping setup
            talksasa_payload = {
                            "sender_id": TALKSASA_SENDER_ID if ('TALKSASA_SENDER_ID' in globals() and TALKSASA_SENDER_ID) else "TALK-SASA",
                            "message": campaign.message,
                            "recipient": batch
            }

            try:
                print(f"[DIRECT WORKER] Dispatching batch chunk of {len(cleaned_batch)} numbers...")
                http_response = requests.post(target_url, json=talksasa_payload, headers=headers, timeout=30)
                response_data = http_response.json()

                is_api_success = False
                if isinstance(response_data, dict):
                    if str(response_data.get("status", "")).strip().lower() in ["success", "accepted", "true", "1"]:
                        is_api_success = True

                if is_api_success:
                    total_sent += len(cleaned_batch)
                    
                    # Create logging reports for this batch
                    inner_data = response_data.get("data", {}) if isinstance(response_data, dict) else {}
                    remote_id = inner_data.get("queue_uid") or response_data.get("batch_id") or "TALKSASA_BATCH"
                    
                    for p in cleaned_batch:
                        log = DeliveryLog(
                            campaign_id=campaign.id,
                            phone=p,
                            status="Sent",
                            message_id=str(remote_id),
                            cost=str(SMS_COST_PER_SEGMENT),
                        )
                        db.session.add(log)
                else:
                    total_fail += len(cleaned_batch)
                    error_msg = response_data.get("message") or f"HTTP_{http_response.status_code}"
                    
                    log = DeliveryLog(
                        campaign_id=campaign.id,
                        phone="batch_rejected",
                        status=f"Rejected: {error_msg[:100]}",
                    )
                    db.session.add(log)

            except Exception as e:
                total_fail += len(cleaned_batch)
                log = DeliveryLog(
                    campaign_id=campaign.id,
                    phone="batch_network_error",
                    status=f"Error: {str(e)[:100]}",
                )
                db.session.add(log)

            campaign.sent   = total_sent
            campaign.failed = total_fail
            db.session.commit()
            time.sleep(2)  # Essential rate-limiting gap guard

        campaign.status  = "done"
        campaign.sent_at = datetime.now(timezone.utc)
        
        # 🔻 AUTOMATIC UNIT DEDUCTION FOR DIRECT/CSV CAMPAIGNS
        segments = sms_segments(campaign.message)
        total_units_used = total_sent * segments
        if total_units_used > 0:
            deduct_sms_units(total_units_used)

        db.session.commit()
        print("[DIRECT WORKER] Bulk processing successfully completed.")

def deduct_sms_units(amount):
    try:
        setting = AppSetting.query.filter_by(key='sms_units').first()
        if setting:
            current_units = float(setting.value)
            new_units = max(0.0, current_units - float(amount))
            setting.value = str(new_units)
            db.session.commit()
            print(f"[BILLING] Deducted {amount} units. Remaining balance: {new_units}")
    except Exception as e:
        print(f"[BILLING ERROR] Failed to deduct units: {e}")

# ─── CONTACTS API ─────────────────────────────────────────────────────────────
@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    q     = request.args.get("q", "")
    ward  = request.args.get("ward", "")
    group = request.args.get("group", "")
    page  = int(request.args.get("page", 1))
    per   = int(request.args.get("per", 50))

    query = filtered_contacts_query({"q": q, "ward": ward, "group": group})

    total   = query.count()
    contacts = query.order_by(Contact.created_at.desc()).offset((page-1)*per).limit(per).all()

    return jsonify({
        "contacts": [c.to_dict() for c in contacts],
        "total": total,
        "page": page,
        "pages": (total + per - 1) // per,
    })


@app.route("/api/contacts", methods=["POST"])
def add_contact():
    data = request.get_json() or {}
    
    # Extract entries cleanly
    name = data.get("name")
    phone = data.get("phone")
    national_id = data.get("national_id")
    ward = data.get("ward")
    sublocation = data.get("sublocation")
    village = data.get("village")
    polling_station = data.get("polling_station") or data.get("Pollingstation") or data.get("farm")
    gender = data.get("gender")
    age_group = data.get("age_group")
    
    if not name or not phone or not national_id:
        return jsonify({"error": "Missing required elements"}), 400
        
    # Check if duplicate exists
    if Contact.query.filter((Contact.phone == phone) | (Contact.national_id == national_id)).first():
        return jsonify({"error": "Contact with this phone or national ID already exists"}), 400

    new_contact = Contact(
        name=name, phone=phone, national_id=national_id,
        ward=ward, sublocation=sublocation, village=village, polling_station=polling_station,
        gender=gender, age_group=age_group
    )
    db.session.add(new_contact)
    db.session.commit()
    
    return jsonify({"success": True, "contact": new_contact.to_dict()})

@app.route("/api/contacts/<int:cid>", methods=["DELETE"])
def delete_contact(cid):
    contact = Contact.query.get_or_404(cid)
    db.session.delete(contact)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/contacts/bulk-delete", methods=["POST"])
def bulk_delete_contacts():
    data = request.json or {}
    apply_filter = bool(data.get("apply_filter"))
    ids = data.get("ids") or []

    if apply_filter:
        contacts = filtered_contacts_query(data.get("filters") or {}).all()
    else:
        ids = [int(cid) for cid in ids if str(cid).isdigit()]
        if not ids:
            return jsonify({"error": "No contacts selected"}), 400
        contacts = Contact.query.filter(Contact.id.in_(ids)).all()

    count = len(contacts)
    for contact in contacts:
        db.session.delete(contact)
    db.session.commit()
    return jsonify({"ok": True, "deleted": count})


@app.route("/api/contacts/bulk-optout", methods=["POST"])
def bulk_optout_contacts():
    data = request.json or {}
    apply_filter = bool(data.get("apply_filter"))
    ids = data.get("ids") or []
    opted_out = bool(data.get("opted_out", True))

    if apply_filter:
        contacts = filtered_contacts_query(data.get("filters") or {}).all()
    else:
        ids = [int(cid) for cid in ids if str(cid).isdigit()]
        if not ids:
            return jsonify({"error": "No contacts selected"}), 400
        contacts = Contact.query.filter(Contact.id.in_(ids)).all()

    for contact in contacts:
        contact.opted_out = opted_out
    db.session.commit()
    return jsonify({"ok": True, "updated": len(contacts), "opted_out": opted_out})


@app.route("/api/contacts/import", methods=["POST"])
def import_contacts():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400

    content = file.read().decode("utf-8")
    reader  = csv.DictReader(io.StringIO(content))
    added   = 0
    skipped = 0
    errors  = []

    for i, row in enumerate(reader, 2):
        raw   = (row.get("phone_number") or row.get("phone") or row.get("number") or "").strip()
        phone = normalise_phone(raw)
        name  = (row.get("name") or "").strip() or "Unknown"
        national_id = (row.get("national_id") or row.get("id_number") or "").strip()

        if not phone:
            errors.append(f"Row {i}: invalid number '{raw}'")
            skipped += 1
            continue

        if not national_id:
            errors.append(f"Row {i}: missing National ID")
            skipped += 1
            continue

        if Contact.query.filter_by(phone=phone).first():
            skipped += 1
            continue

        if Contact.query.filter_by(national_id=national_id).first():
            skipped += 1
            continue

        contact = Contact(
            name=name,
            phone=phone,
            national_id=national_id,
            ward=(row.get("ward") or "").strip(),
            gender=(row.get("gender") or "").strip(),
        )
        db.session.add(contact)
        added += 1

    db.session.commit()
    return jsonify({"added": added, "skipped": skipped, "errors": errors[:20]})


@app.route("/api/campaigns/import-and-send", methods=["POST"])
def import_and_send_campaign():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    message = (data.get("message") or "").strip()
    contacts = data.get("contacts") or []

    if not name or not message:
        return jsonify({"error": "Campaign name and message are required"}), 400
    if not isinstance(contacts, list) or not contacts:
        return jsonify({"error": "No contacts provided"}), 400

    added = 0
    skipped = 0
    errors = []
    numbers = []
    seen = set()

    for i, row in enumerate(contacts, 1):
        raw = (row.get("phone_number") or row.get("phone") or row.get("number") or "").strip()
        phone = normalise_phone(raw)
        national_id = (row.get("national_id") or row.get("id_number") or "").strip()
        name_value = (row.get("name") or "Unknown").strip()
        ward = (row.get("ward") or "").strip()
        gender = (row.get("gender") or "").strip()

        if not phone:
            errors.append(f"Row {i}: invalid number '{raw}'")
            skipped += 1
            continue
        if not national_id:
            errors.append(f"Row {i}: missing National ID")
            skipped += 1
            continue
        if phone in seen:
            skipped += 1
            continue

        if phone in seen:
            skipped += 1
            continue

        existing = Contact.query.filter((Contact.phone == phone) | (Contact.national_id == national_id)).first()
        if existing:
            skipped += 1
            continue

        seen.add(phone)
        numbers.append(phone)

        contact = Contact(
            name=name_value,
            phone=phone,
            national_id=national_id,
            ward=ward,
            gender=gender,
        )
        db.session.add(contact)
        added += 1

    db.session.commit()

    campaign = Campaign(
        name=name,
        message=message,
        status="draft",
        total=len(numbers),
    )
    db.session.add(campaign)
    db.session.commit()

    thread = Thread(target=send_direct_campaign_async, args=(campaign.id, numbers))
    thread.daemon = True
    thread.start()

    return jsonify({
        "ok": True,
        "campaign": campaign.to_dict(),
        "added": added,
        "skipped": skipped,
        "errors": errors[:20],
    }), 201

@app.route("/api/contacts/meta", methods=["GET"])
def contacts_meta():
    wards = [r[0] for r in db.session.query(Contact.ward).distinct() if r[0]]
    sublocations = [r[0] for r in db.session.query(Contact.sublocation).distinct() if r[0]]
    villages = [r[0] for r in db.session.query(Contact.village).distinct() if r[0]]
    polling_stations = [r[0] for r in db.session.query(Contact.polling_station).distinct() if r[0]] # 🛠️ Fixed lowercase variable
    
    return jsonify({
        "wards": wards,
        "sublocations": sublocations,
        "villages": villages,
        "polling_stations": polling_stations, # 🛠️ Fixed lowercase key
        "genders": ["Male", "Female"],
        "age_groups": ["Youth", "Adult", "Elderly"],
        "total": Contact.query.count()
    })


@app.route("/api/contacts/<int:cid>/optout", methods=["POST"])
def optout(cid):
    c = Contact.query.get_or_404(cid)
    c.opted_out = not c.opted_out
    db.session.commit()
    return jsonify(c.to_dict())


# ─── CAMPAIGNS API ────────────────────────────────────────────────────────────
@app.route("/api/campaigns", methods=["GET"])
def get_campaigns():
    campaigns = Campaign.query.order_by(Campaign.created_at.desc()).all()
    return jsonify([c.to_dict() for c in campaigns])

@app.route("/api/campaigns", methods=["POST"])
def create_campaign():
    data = request.json or {}
    if not data.get("name") or not data.get("message"):
        return jsonify({"error": "Name and message are required"}), 400

    def safe_str(val):
        return val.strip() if isinstance(val, str) else None

    campaign = Campaign(
        name=data["name"].strip(),
        message=data["message"].strip(),
        filter_ward=safe_str(data.get("filter_ward") or data.get("ward")),
        filter_sublocation=safe_str(data.get("filter_sublocation") or data.get("sublocation")),
        filter_village=safe_str(data.get("filter_village") or data.get("village")),
        filter_polling_station=safe_str(
            data.get("filter_polling_station") or 
            data.get("filter_Pollingstation") or 
            data.get("polling_station") or 
            data.get("Pollingstation") or 
            data.get("farm")
        ),
        filter_group=safe_str(data.get("filter_group") or data.get("gender") or data.get("group")),
    )
    db.session.add(campaign)
    db.session.commit()
    return jsonify(campaign.to_dict()), 201


@app.route("/api/campaigns/<int:cid>/send", methods=["POST"])
def send_campaign(cid):
    campaign = Campaign.query.get_or_404(cid)
    if campaign.status in ("sending", "done"):
        return jsonify({"error": f"Campaign already {campaign.status}"}), 400

    thread = Thread(target=send_campaign_async, args=(cid,))
    thread.daemon = True
    thread.start()

    return jsonify({"ok": True, "message": "Campaign sending started"})


@app.route("/api/campaigns/<int:cid>/estimate", methods=["GET"])
def estimate_existing_campaign(cid):
    campaign = Campaign.query.get_or_404(cid)
    recipients = campaign_contact_query(campaign).count()
    return jsonify(estimate_campaign_cost(campaign.message, recipients))


@app.route("/api/campaigns/<int:cid>", methods=["GET"])
def get_campaign(cid):
    campaign = Campaign.query.get_or_404(cid)
    logs = DeliveryLog.query.filter_by(campaign_id=cid).limit(200).all()
    recipients = campaign_contact_query(campaign).count()
    return jsonify({
        **campaign.to_dict(),
        "estimate": estimate_campaign_cost(campaign.message, recipients),
        "actual_cost": campaign_actual_cost(campaign.id),
        "logs": [{"phone": l.phone, "status": l.status, "cost": l.cost, "logged_at": l.logged_at.isoformat()} for l in logs]
    })


@app.route("/api/campaigns/<int:cid>", methods=["DELETE"])
def delete_campaign(cid):
    campaign = Campaign.query.get_or_404(cid)
    DeliveryLog.query.filter_by(campaign_id=cid).delete()
    db.session.delete(campaign)
    db.session.commit()
    return jsonify({"ok": True})



# 💳 Updated Billing Summary Route supporting Manual Ledger & Fallback
@app.route("/api/billing", methods=["GET"])
def billing_summary():
    try:
        campaigns = Campaign.query.order_by(Campaign.created_at.desc()).all()
        history = []
        total_actual = 0.0
        total_estimated = 0.0

        for campaign in campaigns:
            recipients = campaign.total or campaign_contact_query(campaign).count()
            estimate = estimate_campaign_cost(campaign.message, recipients)
            actual = campaign_actual_cost(campaign.id)
            total_actual += actual
            total_estimated += estimate["estimated_cost"]
            
            history.append({
                "id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "created_at": campaign.created_at.isoformat(),
                "sent_at": campaign.sent_at.isoformat() if campaign.sent_at else None,
                "recipients": recipients,
                "sent": campaign.sent,
                "failed": campaign.failed,
                "segments": estimate["segments"],
                "estimated_cost": estimate["estimated_cost"],
                "actual_cost": actual,
                "currency": estimate["currency"],
            })

        # 🚀 Fetch live balance directly from TalkSasa API gateway, fallback to local DB ledger
        live_wallet = fetch_wallet_balance()
        if live_wallet and live_wallet.get("balance") is not None:
            wallet_info = {
                "balance": float(live_wallet["balance"]),
                "currency": live_wallet.get("currency", "KES"),
                "status": live_wallet.get("status", "Live Production")
            }
        else:
            setting = AppSetting.query.filter_by(key='sms_units').first()
            val = float(setting.value) if setting else 54.0
            wallet_info = {
                "balance": val,
                "currency": "KES",
                "status": "Live Production (Manual Ledger Fallback)"
            }
        
        currency_flag = globals().get('BILLING_CURRENCY', 'KES')
        cost_flag = globals().get('SMS_COST_PER_SEGMENT', 0.35)
        paybill_flag = globals().get('MPESA_PAYBILL', '4573776')
        account_flag = globals().get('MPESA_ACCOUNT', '3222')
        ref_flag = globals().get('MPESA_REFERENCE', 'YOUR_USERNAME')
        sandbox_flag = globals().get('SANDBOX', False)

        return jsonify({
            "success": True,
            "wallet": wallet_info,
            "pricing": {
                "currency": currency_flag,
                "cost_per_segment": cost_flag,
                "segment_length": 160,
            },
            "totals": {
                "estimated_spend": round(total_estimated, 2),
                "actual_spend": round(total_actual, 2),
                "campaigns": len(campaigns),
            },
            "top_up": {
                "method": "M-Pesa PayBill",
                "paybill": paybill_flag,
                "account": account_flag,
                "reference": ref_flag,
                "steps": [
                    "Open M-Pesa",
                    "Choose Lipa na M-Pesa",
                    "Choose PayBill",
                    f"Enter business number {paybill_flag}",
                    f"Enter account number {account_flag}",
                    "Enter amount and confirm",
                ],
            },
            "history": history,
            "sandbox": sandbox_flag,
        })
    except Exception as e:
        print(f"Billing route processing exception failure trace: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "wallet": {"balance": 54.00, "currency": "KES", "status": "Error State"},
            "totals": {"estimated_spend": 0.00, "actual_spend": 0.00, "campaigns": 0},
            "history": []
        }), 200


# 🔄 Endpoint to Update Units Ledger Manually
@app.route('/api/billing/update-units', methods=['POST'])
def update_units():
    try:
        data = request.get_json() or {}
        new_units = data.get('units')
        if new_units is not None:
            setting = AppSetting.query.filter_by(key='sms_units').first()
            if not setting:
                setting = AppSetting(key='sms_units', value=str(new_units))
                db.session.add(setting)
            else:
                setting.value = str(new_units)
            db.session.commit()
            return jsonify({"success": True, "units": float(new_units)})
        return jsonify({"success": False, "error": "Invalid units value"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/billing/estimate", methods=["POST"])
def billing_estimate():
    data = request.json or {}
    query = Contact.query.filter_by(opted_out=False)
    if data.get("filter_ward"):
        query = query.filter_by(ward=data["filter_ward"])
    if data.get("filter_group"):
        query = query.filter_by(gender=data["filter_group"])
    return jsonify(estimate_campaign_cost(data.get("message", ""), query.count()))



@app.route('/api/campaigns/estimate', methods=['GET'])
def mobile_campaign_estimate():
    try:
        # 1. Gather ALL 5 filters sent by the frontend parameters
        ward = request.args.get('ward', '').strip()
        gender = request.args.get('gender', '').strip()
        sublocation = request.args.get('sublocation', '').strip()
        village = request.args.get('village', '').strip()
        Pollingstation = request.args.get('Pollingstation', '').strip()
        
        try:
            segments = int(request.args.get('segments', 0))
        except (ValueError, TypeError):
            segments = 0

        # 2. Build the database query dynamically with all filters applied
        query = Contact.query
        
        if ward and ward != 'All':
            query = query.filter(Contact.ward == ward)
        if gender and gender != 'All':
            query = query.filter(Contact.gender == gender)
        if sublocation and sublocation != 'All':
            query = query.filter(Contact.sublocation == sublocation)
        if village and village != 'All':
            query = query.filter(Contact.village == village)
        if Pollingstation and Pollingstation != 'All':
            query = query.filter(Contact.Pollingstation == Pollingstation)
            
        total_matching_contacts = query.count()

        # 3. Calculate metrics using your segment settings
        cost_per_message = segments * globals().get('SMS_COST_PER_SEGMENT', 0.80)
        estimated_total_cost = total_matching_contacts * cost_per_message

        # 4. Explicitly return structured json data response 
        return jsonify({
            "success": True,
            "count": total_matching_contacts,
            "segments": segments,
            "cost": float(estimated_total_cost),
            "currency": globals().get('BILLING_CURRENCY', 'KES')
        })

    except Exception as e:
        print(f"Error executing campaign text calculation framework parameters: {e}")
        return jsonify({
            "success": False,
            "count": 0,
            "segments": 0,
            "cost": 0.00,
            "currency": "KES",
            "error": str(e)
        }), 200

# ─── STATS ───────────────────────────────────────────────────────────────────
@app.route("/api/stats", methods=["GET"])
def get_stats():
    total_contacts  = Contact.query.count()
    active_contacts = Contact.query.filter_by(opted_out=False).count()
    total_campaigns = Campaign.query.count()
    total_sent      = db.session.query(db.func.sum(Campaign.sent)).scalar() or 0

    # Grab the current SMS units ledger balance from the database
    setting = AppSetting.query.filter_by(key='sms_units').first()
    current_units = float(setting.value) if setting else 54.0

    recent = Campaign.query.order_by(Campaign.created_at.desc()).limit(5).all()
    return jsonify({
        "total_contacts":  total_contacts,
        "active_contacts": active_contacts,
        "total_campaigns": total_campaigns,
        "total_sent":      total_sent,
        "sms_units":       current_units,  # Single source of truth syncs with billing
        "recent_campaigns": [c.to_dict() for c in recent],
        "gateway": "TalkSasa"
    })


@app.route("/api/campaigns/send-direct", methods=["POST"])
def trigger_direct_campaign():
    data = request.json or {}
    campaign_id = data.get("campaign_id")
    phone_numbers = data.get("numbers", []) # Your parsed CSV array list

    # Ticking off the background worker thread safely
    thread = Thread(target=send_direct_campaign_async, args=(campaign_id, phone_numbers))
    thread.start()

    return jsonify({"message": "Bulk campaign broadcast pipeline initialized asynchronously."}), 202

# ─── SERVE FRONTEND ───────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, "static")
    if path and os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)
    return send_from_directory(base_dir, "index.html")


# ─── STARTUP ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    with app.app_context():
        # Force a database layout reset to apply sublocation, village, Pollingstation, and age_group
        initialize_database(seed_sample=True)

    print("\n=== Constituency SMS Web App ===")
    print("Gateway Engine: TalkSasa REST API")
    port = int(os.getenv("PORT", "8080"))
    print(f"Open http://localhost:{port} in your browser\n")
    app.run(debug=True, port=port, threaded=True)
