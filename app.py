from flask import Flask, render_template, request, jsonify, session, send_file, send_from_directory
import asyncio
import json
from datetime import datetime

import asyncio
from playwright.async_api import async_playwright
from tools import tax_rate_lookup, address_search, get_pdf_all_reports, Tacoma_report_lookup, King_report_lookup, close_browser , Create_Customer, Check_Existing_Customer, Upload_Attachments, create_work_order, upload_attachments_to_work_order, Accella_report_lookup
import threading
import uuid
import sqlite3
import os
import tempfile
import shutil
import requests

app = Flask(__name__)
app.secret_key = 'lookuptool2025'
# Global variables for browser management
browsers = {}
browsers_initialized = False
browser_init_pid = None
browser_init_lock = threading.Lock()
browser_loop = None
browser_thread = None
browsers_initializing = False
page_locks = {}
playwright_controller = None

async def are_pages_busy(needed_keys):
    """Check on the browser loop if any of the needed page locks are currently held."""
    if not page_locks:
        return False
    for key in needed_keys:
        lock = page_locks.get(key)
        if lock and lock.locked():
            return True
    return False

def update_session_status(session_id, status, error_message=None):
    try:
        if error_message is not None:
            db_execute('UPDATE lookup_sessions SET status = ?, error_message = ? WHERE session_id = ?', (status, error_message, session_id))
        else:
            db_execute('UPDATE lookup_sessions SET status = ? WHERE session_id = ?', (status, session_id))
    except Exception:
        pass

# Use a file-based flag to persist across module reloads
_browser_init_file = os.path.join(os.path.dirname(__file__), '.browsers_initialized')
location_url = ""
property_url = ""
tacoma_url = ""
king_url = ""
accella_url = ""
# Database setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'lookup_sessions.db')
LANDING_BUILD_DIR = os.path.join(BASE_DIR, 'sterling-septic-landing-page', 'build')
async def start_browsers():
    global browsers, browsers_initialized, browser_init_pid, browser_init_lock, browsers_initializing
    global playwright_controller
    
    # Use file-based lock to persist across module reloads
    lock_file_path = os.path.join(os.path.dirname(__file__), '.browser_init.lock')
    current_pid = os.getpid()
    
    print(f"Starting browsers - PID: {current_pid}, Current browsers dict: {list(browsers.keys())}, browsers_initialized: {browsers_initialized}")
    
    # Idempotent: if already initialized, reuse
    if browsers_initialized and browsers:
        print("Browsers already initialized in this process, reusing existing instances")
        return
    
    # If initialization already in progress, wait for it
    if browsers_initializing:
        print("Browsers initialization already in progress, waiting...")
        while browsers_initializing and not browsers_initialized:
            await asyncio.sleep(0.1)
        return
    
    browsers_initializing = True
    
    # Proceed with browser initialization
    print(f"Proceeding with browser initialization in PID: {current_pid}")
    
    # Platform-specific browser arguments
    import platform
    system = platform.system().lower()
    
    if system == "windows":
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor"
        ]
    elif system == "linux":
        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"
        ]
    else:  # macOS
        args = [
            # "--disable-gpu",
            # "--disable-dev-shm-usage",
            # "--disable-blink-features=AutomationControlled",
            # "--start-maximized",
            # "--window-size=1200,800"
        ]
    
    # Start Playwright controller (reuse if already started)
    if playwright_controller is None:
        playwright_controller = await async_playwright().start()
    print("Creating single browser instance with multiple contexts...")
    
    # Create a single browser instance
    browsers['main_browser'] = await playwright_controller.chromium.launch(
        headless=False, 
        args=args,
        # slow_mo=1000,  # Add delay to make browser more visible
        channel=None,  # Use system Chrome if available
        executable_path=None  # Let Playwright find the executable
    )
    print("Created main browser instance")
    
    # Create separate contexts for different tasks
    browsers['location_context'] = await browsers['main_browser'].new_context()
    browsers['property_context'] = await browsers['main_browser'].new_context()
    browsers['tacoma_context'] = await browsers['main_browser'].new_context()
    browsers['king_context'] = await browsers['main_browser'].new_context()
    browsers['customer_context'] = await browsers['main_browser'].new_context()
    browsers['accella_context'] = await browsers['main_browser'].new_context()
    # Create pages from contexts
    browsers['location_page'] = await browsers['location_context'].new_page()
    browsers['property_page'] = await browsers['property_context'].new_page()
    browsers['tacoma_page'] = await browsers['tacoma_context'].new_page()
    browsers['king_page'] = await browsers['king_context'].new_page()
    browsers['customer_page'] = await browsers['customer_context'].new_page()
    browsers['accella_page'] = await browsers['accella_context'].new_page()
    print("Created 5 contexts and pages from single browser")
    print(f"Browser is running: {browsers['main_browser'].is_connected()}")
    print(f"Browser version: {browsers['main_browser'].version}")
    
    # Add a small delay to ensure browser window is visible
    await asyncio.sleep(2)
    print("Browser initialization completed, windows should be visible now")

    #load urls
    global location_url
    global property_url
    global tacoma_url
    global king_url
    global accella_url
    location_url = "https://webgis.dor.wa.gov/taxratelookup/SalesTax.aspx"
    property_url = "https://www.onlinerme.com/contractorsearchproperty.aspx"
    tacoma_url = "https://edocs.tpchd.org/"
    king_url = "https://kingcounty.maps.arcgis.com/apps/instant/sidebar/index.html?appid=6c0bbaa4339c4ffab0c53cfe1f8d3d85"
    customer_url = "https://login.fieldedge.com"
    customer_dashboard_url = "https://login.fieldedge.com/#/List/1"
    accella_url = "https://aca-prod.accela.com/TPCHD/Cap/CapHome.aspx?module=EnvHealth&TabName=EnvHealth"
    try :
        await browsers['location_page'].goto(location_url, timeout=3000)
    except Exception as e:
        print(e)
    try :
        await browsers['property_page'].goto(property_url, timeout=3000)
    except Exception as e:
        print(e)
    try :
        await browsers['tacoma_page'].goto(tacoma_url, timeout=3000)
    except Exception as e:
        print(e)
    try :
        await browsers['king_page'].goto(king_url, timeout=3000)
    except Exception as e:
        print(e)
    try :
        await browsers['accella_page'].goto(accella_url, timeout=3000)
    except Exception as e:
        print(e)
    try :
        with open('credentails.json', 'r') as f:
            credentails = json.load(f)
        email = credentails.get('email')
        password = credentails.get('password')
        customer_page = browsers['customer_page']
        await customer_page.goto(customer_url, timeout=60000)
        await customer_page.wait_for_selector("//input[@id='LoginEmail']")
        await customer_page.fill("//input[@id='LoginEmail']",email)
        await customer_page.fill("//input[@id='Password']",password)
        await customer_page.click("//input[@value='Sign in to your account']")
        await customer_page.wait_for_timeout(10000)
        await customer_page.goto(customer_dashboard_url, timeout=30000)
    except Exception as e:
        print(e)
    
    # Initialize per-page locks (idempotent)
    if 'location' not in page_locks:
        page_locks['location'] = asyncio.Lock()
    if 'property' not in page_locks:
        page_locks['property'] = asyncio.Lock()
    if 'tacoma' not in page_locks:
        page_locks['tacoma'] = asyncio.Lock()
    if 'king' not in page_locks:
        page_locks['king'] = asyncio.Lock()
    if 'customer' not in page_locks:
        page_locks['customer'] = asyncio.Lock()
    if 'accella' not in page_locks:
        page_locks['accella'] = asyncio.Lock()
    # Mark browsers as initialized
    browsers_initialized = True
    print(f"Browsers initialization completed. Total browser objects: {len(browsers)} (1 browser, 5 contexts, 5 pages)")
    
    print("Browser initialization completed successfully")
    
    # Clear initializing flag
    browsers_initializing = False

async def close_browsers():
    """Close all browsers, contexts, and pages, and stop Playwright."""
    global browsers, browsers_initialized, browsers_initializing, page_locks, playwright_controller
    # Close pages
    for key in ['location_page', 'property_page', 'tacoma_page', 'king_page', 'customer_page', 'accella_page']:
        try:
            if key in browsers and browsers[key]:
                await browsers[key].close()
        except Exception:
            pass
    # Close contexts
    for key in ['location_context', 'property_context', 'tacoma_context', 'king_context', 'customer_context', 'accella_context']:
        try:
            if key in browsers and browsers[key]:
                await browsers[key].close()
        except Exception:
            pass
    # Close main browser
    try:
        if 'main_browser' in browsers and browsers['main_browser']:
            await browsers['main_browser'].close()
    except Exception:
        pass
    # Reset state
    browsers = {}
    page_locks.clear()
    browsers_initialized = False
    browsers_initializing = False
    # Stop Playwright controller if running
    if playwright_controller is not None:
        try:
            await playwright_controller.stop()
        except Exception:
            pass
        finally:
            playwright_controller = None

@app.route('/api/restart', methods=['POST'])
def restart_browsers():
    """Restart Playwright browsers by closing and reinitializing them on the browser loop."""
    try:
        # Ensure browser loop is running
        start_browser_loop_thread()
        # Close existing browsers and restart
        run_on_browser_loop(close_browsers())
        run_on_browser_loop(start_browsers())
        return jsonify({'status': 'restarted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def start_browser_loop_thread():
    """Start a dedicated asyncio loop thread that owns Playwright and browsers."""
    global browser_thread, browser_loop
    if browser_thread and browser_thread.is_alive():
        return
    
    def _run():
        global browser_loop
        browser_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(browser_loop)
        # Initialize browsers once on this loop
        browser_loop.create_task(start_browsers())
        browser_loop.run_forever()
    
    browser_thread = threading.Thread(target=_run, daemon=True)
    browser_thread.start()
    
    # Wait briefly until browsers are initialized (best-effort)
    import time
    for _ in range(100):  # up to ~10s
        if browsers_initialized:
            break
        time.sleep(0.1)

def run_on_browser_loop(coro):
    """Run a coroutine on the dedicated browser loop and wait for its result."""
    if browser_loop is None:
        raise RuntimeError("Browser loop not started")
    return asyncio.run_coroutine_threadsafe(coro, browser_loop).result()

def init_db():
    """Initialize the database"""
    conn = sqlite3.connect(DATABASE, timeout=30)
    cursor = conn.cursor()
    # Ensure classic DELETE journaling so changes are visible immediately in the main .db file
    try:
        cursor.execute('PRAGMA wal_checkpoint(FULL);')
        cursor.execute('PRAGMA journal_mode=DELETE;')
        cursor.execute('PRAGMA synchronous=NORMAL;')
        cursor.execute('PRAGMA busy_timeout=30000;')
    except Exception:
        pass
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lookup_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            address TEXT NOT NULL,
            city TEXT,
            zip_code TEXT,
            county TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            pdf_urls TEXT,
            multimatch_data TEXT,
            is_multimatch BOOLEAN DEFAULT 0,
            location_code TEXT,
            tacoma_reports TEXT,
            king_reports TEXT,
            error_message TEXT,
            Customer_status TEXT,
            Customer_display_name TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS landing_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            address TEXT,
            system_type TEXT,
            digging_needed TEXT,
            obstacles TEXT,
            service_timeline TEXT,
            service_needed TEXT,
            contact_preference TEXT,
            referral_source TEXT,
            household_size TEXT,
            additional_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Helper to ensure columns exist (idempotent)
    def ensure_columns(table_name, columns):
        try:
            existing_cols = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
            existing_names = {c[1] for c in existing_cols}
            for col in columns:
                name = col.get('name')
                col_type = col.get('type', 'TEXT')
                default = col.get('default')
                if name and name not in existing_names:
                    sql = f"ALTER TABLE {table_name} ADD COLUMN {name} {col_type}"
                    if default is not None:
                        sql += f" DEFAULT {default}"
                    cursor.execute(sql)
        except Exception:
            # Ignore if table doesn't exist yet or ALTER fails; initial create handles schema
            pass

    # Ensure additional/late-added columns
    ensure_columns('lookup_sessions', [
        { 'name': 'king_error_message', 'type': 'TEXT' },
        { 'name': 'Customer_status', 'type': 'TEXT' },
        { 'name': 'Customer_display_name', 'type': 'TEXT' },
        { 'name': 'upload_status', 'type': 'TEXT' },
        { 'name': 'uploaded_files', 'type': 'INTEGER' },
        { 'name': 'work_order_status', 'type': 'TEXT' },
        { 'name': 'work_order_id', 'type': 'TEXT' },
        { 'name': 'work_order_upload_status', 'type': 'TEXT' },
        { 'name': 'work_order_uploaded_files', 'type': 'INTEGER' },
        { 'name': 'accella_reports_path', 'type': 'TEXT' },
        { 'name': 'accella_reports_status', 'type': 'TEXT' },
    ])
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Provide a NEW short-lived connection for legacy call sites that close it."""
    conn = sqlite3.connect(DATABASE, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA busy_timeout=30000;')
        conn.execute('PRAGMA journal_mode=DELETE;')
        conn.execute('PRAGMA synchronous=NORMAL;')
    except Exception:
        pass
    return conn

# Global DB connection and helpers
_global_db_conn = None
_global_db_lock = threading.Lock()

def _get_global_db_connection():
    global _global_db_conn
    if _global_db_conn is None:
        conn = sqlite3.connect(DATABASE, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA busy_timeout=30000;')
            conn.execute('PRAGMA journal_mode=DELETE;')
            conn.execute('PRAGMA synchronous=NORMAL;')
        except Exception:
            pass
        _global_db_conn = conn
    return _global_db_conn

def db_execute(sql, params=()):
    conn = _get_global_db_connection()
    with _global_db_lock:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur

def db_query_one(sql, params=()):
    conn = _get_global_db_connection()
    return conn.execute(sql, params).fetchone()

def db_query_all(sql, params=()):
    conn = _get_global_db_connection()
    return conn.execute(sql, params).fetchall()

# Initialize database on startup
init_db()

# Store lookup sessions (for backward compatibility)
lookup_sessions = {}

# Remove the module-level browser initialization
# asyncio.run(start_browsers())

@app.route('/')
@app.route('/landing')
def landing():
    """Serve the React-based public landing page build."""
    index_path = os.path.join(LANDING_BUILD_DIR, 'index.html')
    if os.path.isfile(index_path):
        return send_from_directory(LANDING_BUILD_DIR, 'index.html')
    # Fallback plain message if build missing
    return "Landing page build not found. Please run npm run build in sterling-septic-landing-page.", 503

@app.route('/landing/<path:filename>')
def landing_static(filename):
    """Serve static assets for the React landing page."""
    file_path = os.path.join(LANDING_BUILD_DIR, filename)
    if os.path.isfile(file_path):
        return send_from_directory(LANDING_BUILD_DIR, filename)
    return jsonify({'error': 'Asset not found'}), 404

@app.route('/vite.svg')
def landing_vite_svg():
    """Serve the Vite favicon used by the React landing page."""
    file_path = os.path.join(LANDING_BUILD_DIR, 'vite.svg')
    if os.path.isfile(file_path):
        return send_from_directory(LANDING_BUILD_DIR, 'vite.svg')
    return jsonify({'error': 'Asset not found'}), 404

@app.route('/leads')
def leads():
    """Admin view for landing page leads."""
    page = max(int(request.args.get('page', 1)), 1)
    per_page = 20
    offset = (page - 1) * per_page

    rows = db_query_all('SELECT COUNT(*) as total FROM landing_leads')
    total = rows[0]['total'] if rows else 0
    total_pages = max((total + per_page - 1) // per_page, 1)

    leads_rows = db_query_all(
        'SELECT * FROM landing_leads ORDER BY created_at DESC LIMIT ? OFFSET ?',
        (per_page, offset)
    )
    leads_list = [dict(row) for row in leads_rows]

    return render_template('leads.html',
                           leads=leads_list,
                           page=page,
                           per_page=per_page,
                           total=total,
                           total_pages=total_pages)

@app.route('/api/leads', methods=['POST'])
def create_lead():
    """Capture a lead submitted from the public landing page."""
    try:
        data = request.get_json(silent=True) or request.form.to_dict()

        def clean_value(key):
            value = data.get(key, '')
            return value.strip() if isinstance(value, str) else value

        required_fields = {
            'full_name': 'Name',
            'phone': 'Phone',
            'email': 'Email'
        }
        missing_labels = [
            label for key, label in required_fields.items()
            if not clean_value(key)
        ]
        if missing_labels:
            return jsonify({'error': f"Missing required field(s): {', '.join(missing_labels)}"}), 400

        db_execute(
            '''
            INSERT INTO landing_leads (
                full_name,
                phone,
                email,
                address,
                system_type,
                digging_needed,
                obstacles,
                service_timeline,
                service_needed,
                contact_preference,
                referral_source,
                household_size,
                additional_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                clean_value('full_name'),
                clean_value('phone'),
                clean_value('email'),
                clean_value('address'),
                clean_value('system_type'),
                clean_value('digging_needed'),
                clean_value('obstacles'),
                clean_value('service_timeline'),
                clean_value('service_needed'),
                clean_value('contact_preference'),
                clean_value('referral_source'),
                clean_value('household_size'),
                clean_value('additional_notes')
            )
        )

        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _lead_to_dict(row):
    return {
        'id': row['id'],
        'full_name': row['full_name'],
        'phone': row['phone'],
        'email': row['email'],
        'address': row['address'],
        'system_type': row['system_type'],
        'digging_needed': row['digging_needed'],
        'obstacles': row['obstacles'],
        'service_timeline': row['service_timeline'],
        'service_needed': row['service_needed'],
        'contact_preference': row['contact_preference'],
        'referral_source': row['referral_source'],
        'household_size': row['household_size'],
        'additional_notes': row['additional_notes'],
        'created_at': row['created_at'],
    }

@app.route('/api/leads/<int:lead_id>', methods=['GET', 'PUT'])
def lead_detail(lead_id):
    """Retrieve or update a specific lead entry."""
    row = db_query_one('SELECT * FROM landing_leads WHERE id = ?', (lead_id,))
    if not row:
        return jsonify({'error': 'Lead not found'}), 404

    if request.method == 'GET':
        return jsonify(_lead_to_dict(row))

    data = request.get_json(force=True) or {}
    required_fields = ['full_name', 'phone', 'email']
    for field in required_fields:
        value = (data.get(field) or '').strip()
        if not value:
            return jsonify({'error': f'{field.replace("_", " ").title()} is required'}), 400

    update_fields = [
        'full_name', 'phone', 'email', 'address', 'system_type', 'digging_needed',
        'obstacles', 'service_timeline', 'service_needed', 'contact_preference',
        'referral_source', 'household_size', 'additional_notes'
    ]
    assignments = ', '.join(f"{field} = ?" for field in update_fields)
    params = [data.get(field, '') for field in update_fields]
    params.append(lead_id)
    db_execute(f'UPDATE landing_leads SET {assignments} WHERE id = ?', tuple(params))

    updated_row = db_query_one('SELECT * FROM landing_leads WHERE id = ?', (lead_id,))
    return jsonify(_lead_to_dict(updated_row))

@app.route('/dashboard')
def dashboard():
    """Dashboard page showing overview and recent lookups"""
    # Load sessions from DB to render without client API calls
    rows = db_query_all('SELECT * FROM lookup_sessions ORDER BY start_time DESC')

    lookups = [dict(r) for r in rows]
    # Preprocess JSON fields minimally for any consumer (not strictly needed for counts)
    for item in lookups:
        for key in ('pdf_urls', 'multimatch_data', 'tacoma_reports', 'king_reports'):
            if item.get(key) and isinstance(item.get(key), str):
                try:
                    item[key] = json.loads(item[key])
                except Exception:
                    item[key] = []

    # Compute stats
    total = len(lookups)
    completed = sum(1 for s in lookups if s.get('status') == 'completed')
    running = sum(1 for s in lookups if s.get('status') in ('running', 'waiting'))
    failed = sum(1 for s in lookups if s.get('status') == 'error')

    # Recent 5
    recent_lookups = lookups[:5]

    return render_template(
        'dashboard.html',
        stats={
            'total': total,
            'completed': completed,
            'running': running,
            'failed': failed
        },
        recent_lookups=recent_lookups
    )

@app.route('/lookup')
def lookup_tool():
    """Lookup tool page"""
    return render_template('lookup.html')

@app.route('/results')
def results():
    """Results page - shows results for specific lookup session"""
    session_id = request.args.get('session_id')
    session_data = None
    
    if session_id:
        # Try database first
        db_session = db_query_one('SELECT * FROM lookup_sessions WHERE session_id = ?', (session_id,))
        
        if db_session:
            session_data = dict(db_session)
            # Parse JSON-like fields for direct template rendering
            for key in ('pdf_urls', 'multimatch_data', 'tacoma_reports', 'king_reports'):
                try:
                    if session_data.get(key):
                        session_data[key] = json.loads(session_data[key])
                except Exception:
                    session_data[key] = []
        elif session_id in lookup_sessions:
            session_data = lookup_sessions[session_id]
        else:
            session_data = {
                'error': 'Session not found or expired',
                'session_id': session_id
            }
    
    return render_template('results.html', session_data=session_data)

@app.route('/customer/create')
def customer_create():
    """Standalone customer creation page, optionally prefilled by session_id."""
    session_id = request.args.get('session_id')
    session_data = None
    if session_id:
        try:
            conn = get_db_connection()
            row = conn.execute('SELECT * FROM lookup_sessions WHERE session_id = ?', (session_id,)).fetchone()
            conn.close()
            if row:
                session_data = dict(row)
        except Exception:
            session_data = None
    return render_template('customer_create.html', session_data=session_data)

@app.route('/all-lookups')
def all_lookups():
    """All lookups page showing all lookup sessions"""
    lookups = db_query_all('SELECT * FROM lookup_sessions ORDER BY start_time DESC')
    
    # Convert to list of dictionaries
    lookups_list = [dict(lookup) for lookup in lookups]
    
    return render_template('all_lookups.html', lookups=lookups_list)

@app.route('/api/lookup', methods=['POST'])
def start_lookup():
    """Start a new lookup process"""
    try:

        data = request.get_json()
        address_line_1 = data.get('address_line_1', '')
        if "," in address_line_1:
            address_line_1, city, zip_code = address_line_1.split(",")
            city = city.strip()
            zip_code = zip_code.split(" ")[-1]
            # check zipcode is number
            if not zip_code.isdigit():
                zip_code = data.get('zip_code', '')
            county = data.get('county', '')
        else:
            city = data.get('city', '')
            zip_code = data.get('zip_code', '')
            county = data.get('county', '')
        
        if not address_line_1:
            return jsonify({'error': 'Address is required'}), 400
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Store session data in database
        conn = get_db_connection()
        # Decide initial status based on page locks (best-effort via browser loop)
        initial_status = 'running'
        def _check_busy():
            # This function runs on the browser loop to check lock state
            if not page_locks:
                return False
            needed = ['property']  # always need property; optionally add others below
            if city and zip_code:
                needed.append('location')
            if county.lower() == 'pierce':
                needed.append('tacoma')
            elif county.lower() == 'king':
                needed.append('king')
            for key in needed:
                lock = page_locks.get(key)
                if lock and lock.locked():
                    return True
            return False
        
        # If browser loop exists, query it; otherwise assume running
        try:
            if browser_loop is not None:
                busy = asyncio.run_coroutine_threadsafe(are_pages_busy(['property']), browser_loop).result(timeout=0.5)
                # refine with dynamic set
                needed_keys = ['property']
                if city and zip_code:
                    needed_keys.append('location')
                if county.lower() == 'pierce':
                    needed_keys.append('tacoma')
                    needed_keys.append('accella')
                elif county.lower() == 'king':
                    needed_keys.append('king')
                busy = asyncio.run_coroutine_threadsafe(are_pages_busy(needed_keys), browser_loop).result(timeout=0.5)
                if busy:
                    initial_status = 'waiting'
        except Exception:
            pass

        db_execute('INSERT INTO lookup_sessions (session_id, address, city, zip_code, county, status) VALUES (?, ?, ?, ?, ?, ?)', (session_id, address_line_1, city, zip_code, county, initial_status))
        
        # Store session data in memory (for backward compatibility)
        lookup_sessions[session_id] = {
            'status': initial_status,
            'start_time': datetime.now().isoformat(),
            'address': address_line_1,
            'city': city,
            'zip_code': zip_code,
            'county': county,
            'results': None,
            'error': None
        }
        
        # Start lookup in background thread
        
        thread = threading.Thread(target=run_lookup, args=(session_id, address_line_1, city, zip_code, county))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'session_id': session_id, 
            'status': 'started',
            'redirect_url': f'/results?session_id={session_id}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-pdfs', methods=['POST'])
def upload_pdfs():
    try:
        start_browser_loop_thread()
        data = request.get_json(force=True) or {}
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id required'}), 400

        # Collect URLs from DB
        row = db_query_one('SELECT address, pdf_urls, tacoma_reports, king_reports FROM lookup_sessions WHERE session_id = ?', (session_id,))
        if not row:
            return jsonify({'error': 'Session not found'}), 404

        address_line_1 = row['address']
        items = []  # list of { 'url': str, 'name': str }
        try:
            if row['pdf_urls']:
                rme_list = json.loads(row['pdf_urls'])
                for entry in rme_list:
                    parts = (entry or '').split(',')
                    url = (parts[0] if len(parts) > 0 else '').strip()
                    rme_type = (parts[1] if len(parts) > 1 else '').strip().replace(' ', '_') or 'report'
                    rme_date = (parts[2] if len(parts) > 2 else '').strip().replace('/', '-') or 'date'
                    if url:
                        name = f"rme_{rme_type}_{rme_date}.pdf"
                        items.append({'url': url, 'name': name})
        except Exception:
            pass
        try:
            if row['tacoma_reports']:
                tpchd_list = json.loads(row['tacoma_reports'])
                for i, entry in enumerate(tpchd_list, 1):
                    parts = (entry or '').split(',')
                    url = (parts[0] if len(parts) > 0 else '').strip()
                    tp_type = (parts[1] if len(parts) > 1 else '').strip().replace(' ', '_') or 'report'
                    if url:
                        name = f"tpchd_{tp_type}_{i}.pdf"
                        items.append({'url': url, 'name': name})
        except Exception:
            pass
        try:
            if row['king_reports']:
                k_list = json.loads(row['king_reports'])
                for i, url in enumerate(k_list, 1):
                    url = (url or '').strip()
                    if url:
                        name = f"king_report_{i}.pdf"
                        items.append({'url': url, 'name': name})
        except Exception:
            pass

        if not items:
            try:
                db_execute('UPDATE lookup_sessions SET upload_status = ? WHERE session_id = ?', ('No reports found to upload', session_id))
            except Exception:
                pass
            return jsonify({'error': 'No report URLs found for this session'}), 400

        # Download PDFs to temp dir
        tmpdir = tempfile.mkdtemp(prefix=f"attach_{session_id}_")
        session_http = requests.Session()
        session_http.headers.update({
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/pdf,application/octet-stream,*/*;q=0.8'
        })
        file_paths = []
        for it in items:
            try:
                r = session_http.get(it['url'], timeout=30, allow_redirects=True)
                data = r.content
                # simple PDF sniff
                if not (r.headers.get('Content-Type','').lower().startswith('application/pdf') or data[:4] == b'%PDF'):
                    continue
                safe_name = ''.join(c for c in it['name'] if c.isalnum() or c in ('-', '_', '.'))
                if not safe_name.endswith('.pdf'):
                    safe_name += '.pdf'
                fname = os.path.join(tmpdir, safe_name)
                with open(fname, 'wb') as f:
                    f.write(data)
                file_paths.append(fname)
            except Exception:
                continue

        if not file_paths:
            try:
                db_execute('UPDATE lookup_sessions SET upload_status = ? WHERE session_id = ?', ('Failed to download PDFs', session_id))
            except Exception:
                pass
            return jsonify({'error': 'Failed to download any PDFs'}), 500

        async def run_upload():
            if not browsers_initialized:
                await start_browsers()
            page = browsers.get('customer_page')
            if page is None:
                main_browser = browsers.get('main_browser')
                if main_browser:
                    browsers['customer_context'] = await main_browser.new_context()
                    browsers['customer_page'] = await browsers['customer_context'].new_page()
                    page = browsers['customer_page']
            uploaded, failed = await Upload_Attachments(page, address_line_1, file_paths)
            await close_browser(page, 'https://login.fieldedge.com/#/List/1')
            return {'count': uploaded, 'failed': failed, 'dir': tmpdir}

        result = run_on_browser_loop(run_upload())
        # Persist status
        try:
            db_execute('UPDATE lookup_sessions SET upload_status = ?, uploaded_files = ? WHERE session_id = ?', (f"Uploaded {result.get('count', 0)} file(s), Failed {result.get('failed', 0)}", result.get('count', 0), session_id))
        except Exception:
            pass
        # Clean up temp dir after upload
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
        return jsonify({'status': 'ok', 'uploaded': result.get('count', 0), 'failed': result.get('failed', 0)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-workorder-pdfs', methods=['POST'])
def upload_workorder_pdfs():
    try:
        start_browser_loop_thread()
        data = request.get_json(force=True) or {}
        session_id = data.get('session_id')
        override_wo = (data.get('work_order_id') or '').strip() or None
        if not session_id:
            return jsonify({'error': 'session_id required'}), 400

        # Collect URLs and Work Order from DB
        row = db_query_one('SELECT address, pdf_urls, tacoma_reports, king_reports, work_order_id FROM lookup_sessions WHERE session_id = ?', (session_id,))
        if not row:
            return jsonify({'error': 'Session not found'}), 404

        work_order_id = override_wo or (row['work_order_id'] or '').strip()
        if not work_order_id:
            return jsonify({'error': 'No work order ID found for this session'}), 400

        address_line_1 = row['address']
        items = []  # list of { 'url': str, 'name': str }
        try:
            if row['pdf_urls']:
                rme_list = json.loads(row['pdf_urls'])
                for entry in rme_list:
                    parts = (entry or '').split(',')
                    url = (parts[0] if len(parts) > 0 else '').strip()
                    rme_type = (parts[1] if len(parts) > 1 else '').strip().replace(' ', '_') or 'report'
                    rme_date = (parts[2] if len(parts) > 2 else '').strip().replace('/', '-') or 'date'
                    if url:
                        name = f"rme_{rme_type}_{rme_date}.pdf"
                        items.append({'url': url, 'name': name})
        except Exception:
            pass
        try:
            if row['tacoma_reports']:
                tpchd_list = json.loads(row['tacoma_reports'])
                for i, entry in enumerate(tpchd_list, 1):
                    parts = (entry or '').split(',')
                    url = (parts[0] if len(parts) > 0 else '').strip()
                    tp_type = (parts[1] if len(parts) > 1 else '').strip().replace(' ', '_') or 'report'
                    if url:
                        name = f"tpchd_{tp_type}_{i}.pdf"
                        items.append({'url': url, 'name': name})
        except Exception:
            pass
        try:
            if row['king_reports']:
                k_list = json.loads(row['king_reports'])
                for i, url in enumerate(k_list, 1):
                    url = (url or '').strip()
                    if url:
                        name = f"king_report_{i}.pdf"
                        items.append({'url': url, 'name': name})
        except Exception:
            pass

        if not items:
            try:
                db_execute('UPDATE lookup_sessions SET upload_status = ? WHERE session_id = ?', ('No reports found to upload', session_id))
            except Exception:
                pass
            return jsonify({'error': 'No report URLs found for this session'}), 400

        # Download PDFs to temp dir
        tmpdir = tempfile.mkdtemp(prefix=f"wo_attach_{session_id}_")
        session_http = requests.Session()
        session_http.headers.update({
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/pdf,application/octet-stream,*/*;q=0.8'
        })
        file_paths = []
        for it in items:
            try:
                r = session_http.get(it['url'], timeout=30, allow_redirects=True)
                data = r.content
                if not (r.headers.get('Content-Type','').lower().startswith('application/pdf') or data[:4] == b'%PDF'):
                    continue
                safe_name = ''.join(c for c in it['name'] if c.isalnum() or c in ('-', '_', '.'))
                if not safe_name.endswith('.pdf'):
                    safe_name += '.pdf'
                fname = os.path.join(tmpdir, safe_name)
                with open(fname, 'wb') as f:
                    f.write(data)
                file_paths.append(fname)
            except Exception:
                continue

        if not file_paths:
            try:
                db_execute('UPDATE lookup_sessions SET upload_status = ? WHERE session_id = ?', ('Failed to download PDFs', session_id))
            except Exception:
                pass
            return jsonify({'error': 'Failed to download any PDFs'}), 500

        async def run_upload_to_wo():
            if not browsers_initialized:
                await start_browsers()
            page = browsers.get('customer_page')
            if page is None:
                main_browser = browsers.get('main_browser')
                if main_browser:
                    browsers['customer_context'] = await main_browser.new_context()
                    browsers['customer_page'] = await browsers['customer_context'].new_page()
                    page = browsers['customer_page']
            status_text, uploaded = await upload_attachments_to_work_order(page, 'https://login.fieldedge.com/#/List/1', address_line_1, file_paths, work_order_id)
            await close_browser(page, 'https://login.fieldedge.com/#/List/1')
            # status_text expected like 'Uploaded Successfully' or 'Error'
            failed = max(0, len(file_paths) - (uploaded or 0))
            return {'text': status_text, 'count': uploaded or 0, 'failed': failed, 'dir': tmpdir}

        result = run_on_browser_loop(run_upload_to_wo())
        try:
            db_execute('UPDATE lookup_sessions SET work_order_upload_status = ?, work_order_uploaded_files = ? WHERE session_id = ?', (f"{result.get('text', '')}: Uploaded {result.get('count', 0)} file(s), Failed {result.get('failed', 0)}", result.get('count', 0), session_id))
        except Exception:
            pass
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
        return jsonify({'status': 'ok', 'uploaded': result.get('count', 0), 'failed': result.get('failed', 0)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/create-work-order', methods=['POST'])
def api_create_work_order():
    try:
        start_browser_loop_thread()
        data = request.get_json(force=True) or {}
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id required'}), 400
        # Fetch session for address
        row = db_query_one('SELECT address FROM lookup_sessions WHERE session_id = ?', (session_id,))
        if not row:
            return jsonify({'error': 'Session not found'}), 404
        address_line_1 = row['address']

        order_form_data = {
            'immediate': (data.get('immediate') or '').strip(),
            'task': (data.get('task') or '').strip(),
            'task_duration': (data.get('task_duration') or '').strip(),
            'priority': (data.get('priority') or '').strip(),
            'lead_source': (data.get('lead_source') or '').strip(),
            'primary_tech': (data.get('primary_tech') or '').strip(),
            'start_date': (data.get('start_date') or '').strip(),
            'start_time': (data.get('start_time') or '').strip(),
            'customer_po': (data.get('customer_po') or '').strip(),
            'description': (data.get('description') or '').strip(),
            'tags': (data.get('tags') or '').strip(),
        }

        async def run_create_wo():
            if not browsers_initialized:
                await start_browsers()
            page = browsers.get('customer_page')
            if page is None:
                main_browser = browsers.get('main_browser')
                if main_browser:
                    browsers['customer_context'] = await main_browser.new_context()
                    browsers['customer_page'] = await browsers['customer_context'].new_page()
                    page = browsers['customer_page']
            status_text, work_order_number = await create_work_order(page, 'https://login.fieldedge.com/#/List/1', address_line_1, order_form_data)
            await close_browser(page, 'https://login.fieldedge.com/#/List/1')
            return {'text': status_text, 'number': work_order_number}

        result = run_on_browser_loop(run_create_wo())
        # Persist to DB
        try:
            db_execute('UPDATE lookup_sessions SET work_order_status = ?, work_order_id = ? WHERE session_id = ?', (result.get('text'), result.get('number'), session_id))
        except Exception:
            pass
        return jsonify({'status': 'ok', 'text': result.get('text'), 'work_order_number': result.get('number')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/lookup/<session_id>')
def get_lookup_status(session_id):
    """Get lookup status and results"""
    # Try database first
    db_session = db_query_one('SELECT * FROM lookup_sessions WHERE session_id = ?', (session_id,))
    
    if db_session:
        session_data = dict(db_session)
        # Convert JSON strings back to objects
        if session_data['pdf_urls']:
            try:
                session_data['pdf_urls'] = json.loads(session_data['pdf_urls'])
            except:
                session_data['pdf_urls'] = []
        if session_data['multimatch_data']:
            try:
                session_data['multimatch_data'] = json.loads(session_data['multimatch_data'])
            except:
                session_data['multimatch_data'] = []
        if session_data['tacoma_reports']:
            try:
                session_data['tacoma_reports'] = json.loads(session_data['tacoma_reports'])
            except:
                session_data['tacoma_reports'] = []
        if session_data['king_reports']:
            try:
                session_data['king_reports'] = json.loads(session_data['king_reports'])
            except:
                session_data['king_reports'] = []
        
        return jsonify(session_data)
    
    # Fallback to memory storage
    if session_id not in lookup_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    return jsonify(lookup_sessions[session_id])

@app.route('/api/lookup/<session_id>/cancel', methods=['POST'])
def cancel_lookup(session_id):
    """Cancel a running lookup"""
    try:
        # Update database first
        existing = db_query_one('SELECT status FROM lookup_sessions WHERE session_id = ?', (session_id,))
        
        if not existing:
            
            return jsonify({'error': 'Session not found'}), 404
        
        # Only update if not already completed/cancelled
        current_status = existing['status']
        if current_status not in ('completed', 'cancelled'):
            db_execute('UPDATE lookup_sessions SET status = ?, error_message = ? WHERE session_id = ?', ('cancelled', 'Lookup cancelled by user', session_id))

        # Update memory storage if present
        if session_id in lookup_sessions:
            lookup_sessions[session_id]['status'] = 'cancelled'
            lookup_sessions[session_id]['error'] = 'Lookup cancelled by user'
        
        return jsonify({'status': 'cancelled'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/lookup/<session_id>/delete', methods=['DELETE'])
def delete_lookup(session_id):
    """Delete a lookup session"""
    try:
        # Check if session exists and get its status
        session_data = db_query_one('SELECT * FROM lookup_sessions WHERE session_id = ?', (session_id,))
        
        if not session_data:
            return jsonify({'error': 'Session not found'}), 404
        
        session_dict = dict(session_data)
        
        # If session is running, mark it as cancelled to signal browser cleanup
        if session_dict['status'] == 'running':
            # Update status to cancelled in database
            db_execute('UPDATE lookup_sessions SET status = ?, error_message = ? WHERE session_id = ?', ('cancelled', 'Lookup cancelled by user', session_id))
            
            # Update status in memory storage if exists
            if session_id in lookup_sessions:
                lookup_sessions[session_id]['status'] = 'cancelled'
                lookup_sessions[session_id]['error'] = 'Lookup cancelled by user'
        
        # Delete from database
        db_execute('DELETE FROM lookup_sessions WHERE session_id = ?', (session_id,))
        
        # Delete from memory storage if exists
        if session_id in lookup_sessions:
            del lookup_sessions[session_id]
        
        return jsonify({'status': 'deleted', 'message': 'Lookup deleted successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-accella/<session_id>')
def download_accella(session_id):
    """Download the Accella report PDF for a session, if available."""
    try:
        row = db_query_one('SELECT accella_reports_path FROM lookup_sessions WHERE session_id = ?', (session_id,))
        if not row:
            return jsonify({'error': 'Session not found'}), 404
        file_path = (row['accella_reports_path'] or '').strip()
        if not file_path:
            return jsonify({'error': 'No Accella report available for this session'}), 404
        if not os.path.isfile(file_path):
            return jsonify({'error': 'Accella report file not found on server'}), 404
        # Serve inline for iframe display (no forced download)
        return send_file(file_path, mimetype='application/pdf', as_attachment=False, download_name=os.path.basename(file_path))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def is_session_cancelled(session_id):
    """Check if the session has been cancelled"""
    # Check memory storage first
    if session_id in lookup_sessions:
        return lookup_sessions[session_id].get('status') == 'cancelled'
    
    # Check database
    try:
        session_data = db_query_one('SELECT status FROM lookup_sessions WHERE session_id = ?', (session_id,))
        
        if session_data:
            return session_data['status'] == 'cancelled'
    except:
        pass
    
    return False

def run_lookup(session_id, address_line_1, city, zip_code, county):
    """Run the lookup process in a separate thread with multithreading"""
    try:
        # Ensure browser loop thread is running
        start_browser_loop_thread()
        
        async def async_lookup():
            # Check if cancelled before starting
            if is_session_cancelled(session_id):
                print(f"Session {session_id} was cancelled before starting")
                return
            
            # Parse address
            address_parts = address_line_1.split(" ")
            street_number = address_parts[0]
            street_name = address_parts[1]
            
            # Ensure browsers are initialized on the dedicated loop
            print(f"Ensuring browsers are initialized for session {session_id}")
            await start_browsers()
            
            # Create separate browser instances for different tasks
            location_tool = None
            property_tool = None
            county_tool = None
            accella_tool = None
            
            try:                
                # Update status to running when acquiring first needed lock
                update_session_status(session_id, 'running')
                if session_id in lookup_sessions:
                    lookup_sessions[session_id]['status'] = 'running'

                # Task 1: Location code lookup (if city and zip provided)
                if city and zip_code:
                    location_tool = browsers['location_page']
                
                # Task 2: Property report lookup
                property_tool = browsers['property_page']
                
                # Task 3: County reports lookup (Tacoma or King)
                if county.lower() == 'pierce':
                    county_tool = browsers['tacoma_page']
                elif county.lower() == 'king':
                    county_tool = browsers['king_page']
                # Task 4: Accella lookup (Pierce County)
                if county.lower() == 'pierce':
                    accella_tool = browsers['accella_page']
                
                # Check if cancelled after opening browsers
                if is_session_cancelled(session_id):
                    print(f"Session {session_id} was cancelled after opening browsers")
                    # Navigate browsers back to base URLs (keep browsers open)
                    browsers_to_reset = []
                    if location_tool:
                        browsers_to_reset.append(close_browser(location_tool, location_url))
                    if property_tool:
                        browsers_to_reset.append(close_browser(property_tool, property_url))
                    if county_tool:
                        if county.lower() == 'pierce':
                            browsers_to_reset.append(close_browser(county_tool, tacoma_url))
                        elif county.lower() == 'king':
                            browsers_to_reset.append(close_browser(county_tool, king_url))
                    if accella_tool:
                        browsers_to_reset.append(close_browser(accella_tool, accella_url))
                    
                    if browsers_to_reset:
                        await asyncio.gather(*browsers_to_reset, return_exceptions=True)
                    return
                
                # Create tasks for parallel execution after browsers are open
                tasks = []
                if address_line_1:
                    async def run_customer_check():
                        async with page_locks['customer']:
                            status, display_list = await Check_Existing_Customer(
                                browsers['customer_page'], 'https://login.fieldedge.com', address_line_1
                            )
                            try:
                                # navigate back to list to keep session ready
                                await close_browser(browsers['customer_page'], 'https://login.fieldedge.com/#/List/1')
                            except Exception:
                                pass
                            # Persist to DB without overwriting a successful create
                            try:
                                row = db_query_one('SELECT Customer_status FROM lookup_sessions WHERE session_id = ?', (session_id,))
                                existing_status = ((row['Customer_status'] if row else '') or '').strip().lower()
                                new_status = (status or '').strip().lower()
                                display_joined = ', '.join(display_list) if display_list else None
                                # If record already marked as created, do not overwrite
                                if existing_status.startswith('created'):
                                    pass
                                elif new_status.startswith('already'):
                                    db_execute('UPDATE lookup_sessions SET Customer_status = ?, Customer_display_name = ? WHERE session_id = ?', (status, display_joined, session_id))
                                elif (new_status.startswith('not') or new_status == 'no customer exists'):
                                    # Only set NO CUSTOMER EXISTS if empty or previously Not Exists/NO CUSTOMER EXISTS
                                    if existing_status in ('', 'not exists', 'no customer exists'):
                                        db_execute('UPDATE lookup_sessions SET Customer_status = ?, Customer_display_name = ? WHERE session_id = ?', (status, display_joined, session_id))
                                else:
                                    # Fallback: update if we have some other informative status
                                    db_execute('UPDATE lookup_sessions SET Customer_status = ?, Customer_display_name = ? WHERE session_id = ?', (status, display_joined, session_id))
                            except Exception:
                                pass
                            return {'customer_status': status, 'display_names': display_list}
                    tasks.append(asyncio.create_task(run_customer_check()))
                # Task 1: Location code lookup (if city and zip provided)
                if city and zip_code and location_tool:
                    async def run_location():
                        async with page_locks['location']:
                            return await location_lookup_task(browsers['location_page'], location_url, address_line_1, city, zip_code, session_id)
                    location_task = asyncio.create_task(run_location())
                    tasks.append(location_task)
                
                # Task 2: Property report lookup
                if property_tool:
                    async def run_property():
                        async with page_locks['property']:
                            return await property_lookup_task(browsers['property_page'], property_url, street_number, street_name, county, session_id)
                    property_task = asyncio.create_task(run_property())
                    tasks.append(property_task)
                
                # Task 3: County reports lookup (Tacoma or King)
                if county.lower() == 'pierce' and county_tool:
                    async def run_tacoma():
                        async with page_locks['tacoma']:
                            return await tacoma_lookup_task(browsers['tacoma_page'], tacoma_url, street_number, street_name, session_id)
                    county_task = asyncio.create_task(run_tacoma())
                    tasks.append(county_task)
                elif county.lower() == 'king' and county_tool:
                    async def run_king():
                        async with page_locks['king']:
                            return await king_lookup_task(browsers['king_page'], king_url, address_line_1, session_id)
                    county_task = asyncio.create_task(run_king())
                    tasks.append(county_task)
                
                # Task 4: Accella lookup (Pierce only)
                if county.lower() == 'pierce' and accella_tool:
                    async def run_accella():
                        async with page_locks['accella']:
                            return await accella_lookup_task(browsers['accella_page'], accella_url, address_line_1, session_id)
                    accella_task = asyncio.create_task(run_accella())
                    tasks.append(accella_task)
                
                # Run all tasks in parallel
                print(f"Starting {len(tasks)} parallel lookup tasks for session {session_id}")
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                location_code = None
                pdf_urls = []
                multimatch_data = []
                is_multimatch = False
                tacoma_reports = []
                king_reports = []
                accella_reports_status = None
                accella_reports_path = None
                
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(f"Task {i} failed: {result}")
                        continue
                    
                    if result:
                        if 'location_code' in result:
                            location_code = result['location_code']
                        elif 'pdf_urls' in result:
                            pdf_urls = result['pdf_urls']
                            if 'multimatch_data' in result:
                                multimatch_data = result['multimatch_data']
                            if 'is_multimatch' in result:
                                is_multimatch = result['is_multimatch']
                        elif 'tacoma_reports' in result:
                            tacoma_reports = result['tacoma_reports']
                        elif 'king_reports' in result:
                            king_reports = result['king_reports']
                        elif 'accella_reports_status' in result or 'accella_reports_path' in result:
                            accella_reports_status = result.get('accella_reports_status')
                            accella_reports_path = result.get('accella_reports_path')
                
                # Mark as completed
                db_execute('UPDATE lookup_sessions SET status = ?, completed_at = ? WHERE session_id = ?', ('completed', datetime.now().isoformat(), session_id))
                
                # Update memory storage
                lookup_sessions[session_id]['results'] = {
                    'pdf_urls': pdf_urls or [],
                    'multimatch_data': multimatch_data or [],
                    'is_multimatch': is_multimatch,
                    'location_code': location_code,
                    'tacoma_reports': tacoma_reports,
                    'king_reports': king_reports,
                    'accella_reports_status': accella_reports_status,
                    'accella_reports_path': accella_reports_path,
                    'completed_at': datetime.now().isoformat()
                }
                lookup_sessions[session_id]['status'] = 'completed'
                
            except Exception as e:
                error_msg = str(e)
                
                # Save error to database
                db_execute('UPDATE lookup_sessions SET status = ?, error_message = ? WHERE session_id = ?', ('error', error_msg, session_id))
                
                # Update memory storage
                lookup_sessions[session_id]['error'] = error_msg
                lookup_sessions[session_id]['status'] = 'error'
                
                # Navigate browsers back to base URLs on error (keep browsers open)
                browsers_to_reset = []
                if location_tool:
                    browsers_to_reset.append(close_browser(location_tool, location_url))
                if property_tool:
                    browsers_to_reset.append(close_browser(property_tool, property_url))
                if county_tool:
                    if county.lower() == 'pierce':
                        browsers_to_reset.append(close_browser(county_tool, tacoma_url))
                    elif county.lower() == 'king':
                        browsers_to_reset.append(close_browser(county_tool, king_url))
                if accella_tool:
                    browsers_to_reset.append(close_browser(accella_tool, accella_url))
                
                if browsers_to_reset:
                    await asyncio.gather(*browsers_to_reset, return_exceptions=True)
                print(f"All browsers reset to base URLs due to error in session {session_id}")
        
        # Helper function for location code lookup
        async def location_lookup_task(page, url, address_line_1, city, zip_code, session_id):
            try:
                # Check if cancelled before starting
                if is_session_cancelled(session_id):
                    print(f"Location lookup cancelled for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                location_code = await tax_rate_lookup(page, url, address_line_1, city, zip_code)
                
                # Check if cancelled after lookup
                if is_session_cancelled(session_id):
                    print(f"Location lookup cancelled after completion for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                # Update database with location code
                db_execute('UPDATE lookup_sessions SET location_code = ? WHERE session_id = ?', (location_code, session_id))
                
                # Navigate back to base URL instead of closing browser
                await close_browser(page, url)
                print(f"Location browser navigated back for session {session_id}")
                
                return {'location_code': location_code}
            except Exception as e:
                print(f"Location lookup failed: {e}")
                await close_browser(page, url)
                return None
        
        # Helper function for property lookup
        async def property_lookup_task(page, url, street_number, street_name, county, session_id):
            try:
                # Check if cancelled before starting
                if is_session_cancelled(session_id):
                    print(f"Property lookup cancelled for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                # Run address search
                await address_search(page, url, street_number, street_name, county)
                
                # Check if cancelled after address search
                if is_session_cancelled(session_id):
                    print(f"Property lookup cancelled after address search for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                # Get report PDFs and multimatch data
                report_result = await get_pdf_all_reports(page, url)
                
                # Check if cancelled after getting reports
                if is_session_cancelled(session_id):
                    print(f"Property lookup cancelled after getting reports for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                # Extract data from result
                pdf_urls = report_result.get('pdf_urls', [])
                multimatch_data = report_result.get('multimatch_data', [])
                is_multimatch = report_result.get('is_multimatch', False)
                error_message = report_result.get('error_message')
                
                # Update database with all data
                db_execute('UPDATE lookup_sessions SET pdf_urls = ?, multimatch_data = ?, is_multimatch = ?, error_message = ? WHERE session_id = ?', (json.dumps(pdf_urls), json.dumps(multimatch_data), is_multimatch, error_message, session_id))
                
                # Navigate back to base URL instead of closing browser
                await close_browser(page, url)
                print(f"Property browser navigated back for session {session_id}")
                
                return {
                    'pdf_urls': pdf_urls,
                    'multimatch_data': multimatch_data,
                    'is_multimatch': is_multimatch,
                    'error_message': error_message
                }
            except Exception as e:
                print(f"Property lookup failed: {e}")
                await close_browser(page, url)
                return None
        
        # Helper function for Tacoma lookup
        async def tacoma_lookup_task(page, url, street_number, street_name, session_id):
            try:
                # Check if cancelled before starting
                if is_session_cancelled(session_id):
                    print(f"Tacoma lookup cancelled for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                tocoma_address = street_number + " " + street_name
                tacoma_reports = await Tacoma_report_lookup(page, url, tocoma_address)
                
                # Check if cancelled after lookup
                if is_session_cancelled(session_id):
                    print(f"Tacoma lookup cancelled after completion for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                # Update database with Tacoma reports
                db_execute('UPDATE lookup_sessions SET tacoma_reports = ? WHERE session_id = ?', (json.dumps(tacoma_reports), session_id))
                
                # Navigate back to base URL instead of closing browser
                await close_browser(page, url)
                print(f"County browser navigated back for Tacoma reports in session {session_id}")
                
                return {'tacoma_reports': tacoma_reports}
            except Exception as e:
                print(f"Tacoma lookup failed: {e}")
                await close_browser(page, url)
                return None
        
        # Helper function for King County lookup
        async def king_lookup_task(page, url, address_line_1, session_id):
            try:
                # Check if cancelled before starting
                if is_session_cancelled(session_id):
                    print(f"King lookup cancelled for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                king_reports, king_error_message = await King_report_lookup(page, url, address_line_1)
                print(king_error_message)
                # Check if cancelled after lookup
                if is_session_cancelled(session_id):
                    print(f"King lookup cancelled after completion for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                # Update database with King reports and persist king_error_message (do not overwrite global error_message)
                if king_error_message:
                    db_execute('UPDATE lookup_sessions SET king_reports = ?, king_error_message = ? WHERE session_id = ?', (json.dumps(king_reports), king_error_message, session_id))
                else:
                    db_execute('UPDATE lookup_sessions SET king_reports = ? WHERE session_id = ?', (json.dumps(king_reports), session_id))
                
                # Navigate back to base URL instead of closing browser
                await close_browser(page, url)
                print(f"County browser navigated back for King reports in session {session_id}")
                
                return {
                    'king_reports': king_reports,
                    'king_error_message': king_error_message
                }
            except Exception as e:
                print(f"King lookup failed: {e}")
                await close_browser(page, url)
                return None
        
        # Helper function for Accella lookup (Pierce County)
        async def accella_lookup_task(page, url, address_line_1, session_id):
            try:
                # Check if cancelled before starting
                if is_session_cancelled(session_id):
                    print(f"Accella lookup cancelled for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                # Ensure output directory exists
                try:
                    os.makedirs("Accella_Reports", exist_ok=True)
                except Exception:
                    pass
                
                status_text, file_name = await Accella_report_lookup(page, url, session_id, address_line_1)
                
                # Check if cancelled after lookup
                if is_session_cancelled(session_id):
                    print(f"Accella lookup cancelled after completion for session {session_id}")
                    await close_browser(page, url)
                    return None
                
                # Compute saved path if we have a filename
                saved_path = f"Accella_Reports/{file_name}" if (file_name or '').strip() else ""
                try:
                    db_execute('UPDATE lookup_sessions SET accella_reports_status = ?, accella_reports_path = ? WHERE session_id = ?', (status_text or '', saved_path, session_id))
                except Exception:
                    pass
                
                # Navigate back to base URL instead of closing browser
                await close_browser(page, url)
                print(f"Accella browser navigated back for session {session_id}")
                
                return {
                    'accella_reports_status': status_text or '',
                    'accella_reports_path': saved_path
                }
            except Exception as e:
                print(f"Accella lookup failed: {e}")
                await close_browser(page, url)
                return None
        
        # Run the coroutine on the dedicated browser loop
        run_on_browser_loop(async_lookup())
        
    except Exception as e:
        lookup_sessions[session_id]['error'] = str(e)
        lookup_sessions[session_id]['status'] = 'error'

@app.route('/api/sessions')
def get_sessions():
    """Get all lookup sessions"""
    conn = get_db_connection()
    lookups = conn.execute(
        'SELECT * FROM lookup_sessions ORDER BY start_time DESC'
    ).fetchall()
    conn.close()
    
    # Convert to list of dictionaries
    sessions_list = []
    for lookup in lookups:
        session_data = dict(lookup)
        # Convert JSON strings back to objects
        if session_data['pdf_urls']:
            try:
                session_data['pdf_urls'] = json.loads(session_data['pdf_urls'])
            except:
                session_data['pdf_urls'] = []
        if session_data['multimatch_data']:
            try:
                session_data['multimatch_data'] = json.loads(session_data['multimatch_data'])
            except:
                session_data['multimatch_data'] = []
        if session_data['tacoma_reports']:
            try:
                session_data['tacoma_reports'] = json.loads(session_data['tacoma_reports'])
            except:
                session_data['tacoma_reports'] = []
        if session_data['king_reports']:
            try:
                session_data['king_reports'] = json.loads(session_data['king_reports'])
            except:
                session_data['king_reports'] = []
        sessions_list.append(session_data)
    
    return jsonify(sessions_list)
# Quick existing-customer check (no page refresh needed on UI)
@app.route('/api/check-existing', methods=['POST'])
def check_existing():
    # Deprecated: existing-customer check is performed inside run_lookup
    return jsonify({'status': 'disabled', 'display_names': []}), 410



# Create Customer
@app.route('/api/create-customer', methods=['POST'])
def create_customer():
    try:
        # Ensure browser loop is running
        start_browser_loop_thread()

        customer_data = request.get_json(force=True) or {}
        session_id = customer_data.get('session_id')

        async def run_create_customer():
            try:
                # Ensure browsers are initialized
                if not browsers_initialized:
                    await start_browsers()

                # Use dedicated customer page/context
                customer_page = browsers.get('customer_page')
                customer_url = 'https://login.fieldedge.com/#/List/1'
                if customer_page is None:
                    # Prefer creating a new context/page instead of reinitializing all browsers to avoid reloads
                    try:
                        main_browser = browsers.get('main_browser')
                        if main_browser:
                            browsers['customer_context'] = await main_browser.new_context()
                            browsers['customer_page'] = await browsers['customer_context'].new_page()
                            customer_page = browsers['customer_page']
                        else:
                            # Fallback: initialize browsers once
                            await start_browsers()
                            customer_page = browsers.get('customer_page')
                    except Exception:
                        # On failure, initialize browsers once
                        await start_browsers()
                        customer_page = browsers.get('customer_page')

                # Execute creation flow and capture status text
                status_text, display_name = await Create_Customer(customer_page, customer_url, customer_data)
                # Coerce display_name to a plain string for DB/storage compatibility
                if isinstance(display_name, (list, tuple)):
                    display_name_str = ", ".join([d for d in display_name if d])
                else:
                    display_name_str = display_name or ""
                await close_browser(customer_page, customer_url)

                # Persist status in DB when session_id is provided
                print(f"Status text: {status_text}")
                print(f"sessoon id is {session_id}")
                try:
                    if session_id:
                        conn = get_db_connection()
                        conn.execute(
                            'UPDATE lookup_sessions SET Customer_status = ? WHERE session_id = ?',
                            (status_text, session_id)
                        )
                        conn.execute(
                            'UPDATE lookup_sessions SET Customer_display_name = ? WHERE session_id = ?',
                            (display_name_str, session_id)
                        )
                        conn.commit()
                        try:
                            conn.execute('PRAGMA wal_checkpoint(TRUNCATE);')
                        except Exception:
                            pass
                        conn.close()
                except Exception:
                    pass
                return {'status': 'ok', 'text': status_text, 'display_name': display_name_str}
            except Exception as e:
                return {'status': 'error', 'error': str(e)}

        result = run_on_browser_loop(run_create_customer())
        if result.get('status') == 'error':
            # Convert errors to a friendly status string and persist
            status_text = result.get('error', 'Creation Failed')
            display_name = result.get('display_name', '')
            if isinstance(display_name, (list, tuple)):
                display_name = ", ".join([d for d in display_name if d])
            else:
                display_name = display_name or ""
            try:
                if session_id:
                    conn = get_db_connection()
                    conn.execute(
                        'UPDATE lookup_sessions SET Customer_status = ? WHERE session_id = ?',
                        (status_text, session_id)
                    )
                    conn.execute(
                        'UPDATE lookup_sessions SET Customer_display_name = ? WHERE session_id = ?',
                        (display_name, session_id)
                    )
                    conn.commit()
                    try:
                        conn.execute('PRAGMA wal_checkpoint(TRUNCATE);')
                    except Exception:
                        pass
                    conn.close()
            except Exception:
                pass
            return jsonify({'status': 'error', 'text': status_text, 'display_name': display_name}), 500

        # Return JSON with text and display_name for frontend update
        return jsonify({'status': 'ok', 'text': result.get('text') or 'Customer created successfully', 'display_name': result.get('display_name', '')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/customer/create-workorder')
def customer_workorder_create():
    """Combined customer and work order creation page."""
    session_id = request.args.get('session_id')
    session_data = None
    if session_id:
        try:
            conn = get_db_connection()
            row = conn.execute('SELECT * FROM lookup_sessions WHERE session_id = ?', (session_id,)).fetchone()
            conn.close()
            if row:
                session_data = dict(row)
        except Exception:
            session_data = None
    return render_template('customer_workorder_create.html', session_data=session_data)

@app.route('/api/create-customer-workorder', methods=['POST'])
def create_customer_workorder():
    try:
        start_browser_loop_thread()
        data = request.get_json(force=True) or {}
        customer_data = data.get('customer', {})
        work_order_data = data.get('work_order', {})
        session_id = customer_data.get('session_id') or work_order_data.get('session_id')

        if not session_id:
            return jsonify({'error': 'session_id required'}), 400

        # Fetch session for address and reports
        row = db_query_one('SELECT address, pdf_urls, tacoma_reports, king_reports FROM lookup_sessions WHERE session_id = ?', (session_id,))
        if not row:
            return jsonify({'error': 'Session not found'}), 404
        
        address_line_1 = row['address']

        # Prepare items for download (reusing logic from upload_workorder_pdfs)
        items = []
        try:
            if row['pdf_urls']:
                rme_list = json.loads(row['pdf_urls'])
                for entry in rme_list:
                    parts = (entry or '').split(',')
                    url = (parts[0] if len(parts) > 0 else '').strip()
                    rme_type = (parts[1] if len(parts) > 1 else '').strip().replace(' ', '_') or 'report'
                    rme_date = (parts[2] if len(parts) > 2 else '').strip().replace('/', '-') or 'date'
                    if url:
                        name = f"rme_{rme_type}_{rme_date}.pdf"
                        items.append({'url': url, 'name': name})
        except Exception:
            pass
        try:
            if row['tacoma_reports']:
                tpchd_list = json.loads(row['tacoma_reports'])
                for i, entry in enumerate(tpchd_list, 1):
                    parts = (entry or '').split(',')
                    url = (parts[0] if len(parts) > 0 else '').strip()
                    tp_type = (parts[1] if len(parts) > 1 else '').strip().replace(' ', '_') or 'report'
                    if url:
                        name = f"tpchd_{tp_type}_{i}.pdf"
                        items.append({'url': url, 'name': name})
        except Exception:
            pass
        try:
            if row['king_reports']:
                k_list = json.loads(row['king_reports'])
                for i, url in enumerate(k_list, 1):
                    url = (url or '').strip()
                    if url:
                        name = f"king_report_{i}.pdf"
                        items.append({'url': url, 'name': name})
        except Exception:
            pass

        async def run_combined_flow():
            if not browsers_initialized:
                await start_browsers()
            
            # 1. Create Customer
            customer_page = browsers.get('customer_page')
            customer_url = 'https://login.fieldedge.com/#/List/1'
            if customer_page is None:
                main_browser = browsers.get('main_browser')
                if main_browser:
                    browsers['customer_context'] = await main_browser.new_context()
                    browsers['customer_page'] = await browsers['customer_context'].new_page()
                    customer_page = browsers['customer_page']
                else:
                    await start_browsers()
                    customer_page = browsers.get('customer_page')

            cust_status, cust_display = await Create_Customer(customer_page, customer_url, customer_data)
            
            # Coerce display_name
            if isinstance(cust_display, (list, tuple)):
                cust_display_str = ", ".join([d for d in cust_display if d])
            else:
                cust_display_str = cust_display or ""

            # Update DB for customer
            try:
                db_execute('UPDATE lookup_sessions SET Customer_status = ?, Customer_display_name = ? WHERE session_id = ?', (cust_status, cust_display_str, session_id))
            except Exception:
                pass

            if cust_status == "Creation Failed":
                return {'status': 'error', 'error': 'Customer creation failed', 'step': 'customer'}

            # 2. Create Work Order
            # We need to ensure we are back at the list or appropriate state, Create_Customer seems to leave us there or close enough
            # But create_work_order starts by searching address, so it should be fine.
            # However, create_work_order uses `page` which is `customer_page` here.
            
            wo_status, wo_number = await create_work_order(customer_page, customer_url, address_line_1, work_order_data)
            
            try:
                db_execute('UPDATE lookup_sessions SET work_order_status = ?, work_order_id = ? WHERE session_id = ?', (wo_status, wo_number, session_id))
            except Exception:
                pass

            if not wo_number:
                return {'status': 'error', 'error': 'Work Order creation failed', 'step': 'work_order', 'customer_status': cust_status}

            # 3. Upload Documents
            upload_result = {'count': 0, 'failed': 0}
            if items:
                tmpdir = tempfile.mkdtemp(prefix=f"combined_{session_id}_")
                try:
                    session_http = requests.Session()
                    session_http.headers.update({
                        'User-Agent': 'Mozilla/5.0',
                        'Accept': 'application/pdf,application/octet-stream,*/*;q=0.8'
                    })
                    file_paths = []
                    for it in items:
                        try:
                            r = session_http.get(it['url'], timeout=30, allow_redirects=True)
                            data = r.content
                            if not (r.headers.get('Content-Type','').lower().startswith('application/pdf') or data[:4] == b'%PDF'):
                                continue
                            safe_name = ''.join(c for c in it['name'] if c.isalnum() or c in ('-', '_', '.'))
                            if not safe_name.endswith('.pdf'):
                                safe_name += '.pdf'
                            fname = os.path.join(tmpdir, safe_name)
                            with open(fname, 'wb') as f:
                                f.write(data)
                            file_paths.append(fname)
                        except Exception:
                            continue
                    
                    if file_paths:
                        status_text, uploaded_count = await upload_attachments_to_work_order(customer_page, customer_url, address_line_1, file_paths, wo_number)
                        
                        if uploaded_count is None:
                             uploaded_count = 0
                             failed_count = len(file_paths)
                        else:
                             failed_count = len(file_paths) - uploaded_count

                        upload_result['count'] = uploaded_count
                        upload_result['failed'] = failed_count
                        
                        # Update DB
                        status_msg = f"Uploaded {uploaded_count} file(s), Failed {failed_count}"
                        db_execute('UPDATE lookup_sessions SET work_order_upload_status = ?, work_order_uploaded_files = ? WHERE session_id = ?', (status_msg, uploaded_count, session_id))

                finally:
                    shutil.rmtree(tmpdir, ignore_errors=True)

            await close_browser(customer_page, customer_url)
            
            return {
                'status': 'ok',
                'customer_status': cust_status,
                'customer_display': cust_display_str,
                'work_order_status': wo_status,
                'work_order_number': wo_number,
                'upload_result': upload_result
            }

        result = run_on_browser_loop(run_combined_flow())
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Disable debug mode to prevent double browser initialization
    app.run(debug=False, host='0.0.0.0', port=5001)
