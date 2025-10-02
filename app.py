from flask import Flask, render_template, request, jsonify, session
import asyncio
import json
from datetime import datetime
from tools import LookupTool
import threading
import uuid
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'lookuptool2025'

# Database setup
DATABASE = 'lookup_sessions.db'

def init_db():
    """Initialize the database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
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
            location_code TEXT,
            tacoma_reports TEXT,
            error_message TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize database on startup
init_db()

# Store lookup sessions (for backward compatibility)
lookup_sessions = {}

@app.route('/')
def dashboard():
    """Dashboard page showing overview and recent lookups"""
    return render_template('dashboard.html')

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
        conn = get_db_connection()
        db_session = conn.execute(
            'SELECT * FROM lookup_sessions WHERE session_id = ?', (session_id,)
        ).fetchone()
        conn.close()
        
        if db_session:
            session_data = dict(db_session)
        elif session_id in lookup_sessions:
            session_data = lookup_sessions[session_id]
        else:
            session_data = {
                'error': 'Session not found or expired',
                'session_id': session_id
            }
    
    return render_template('results.html', session_data=session_data)

@app.route('/all-lookups')
def all_lookups():
    """All lookups page showing all lookup sessions"""
    conn = get_db_connection()
    lookups = conn.execute(
        'SELECT * FROM lookup_sessions ORDER BY start_time DESC'
    ).fetchall()
    conn.close()
    
    # Convert to list of dictionaries
    lookups_list = [dict(lookup) for lookup in lookups]
    
    return render_template('all_lookups.html', lookups=lookups_list)

@app.route('/api/lookup', methods=['POST'])
def start_lookup():
    """Start a new lookup process"""
    try:
        data = request.get_json()
        address_line_1 = data.get('address_line_1', '')
        city = data.get('city', '')
        zip_code = data.get('zip_code', '')
        county = data.get('county', '')
        
        if not address_line_1:
            return jsonify({'error': 'Address is required'}), 400
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Store session data in database
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO lookup_sessions (session_id, address, city, zip_code, county, status) VALUES (?, ?, ?, ?, ?, ?)',
            (session_id, address_line_1, city, zip_code, county, 'running')
        )
        conn.commit()
        conn.close()
        
        # Store session data in memory (for backward compatibility)
        lookup_sessions[session_id] = {
            'status': 'running',
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

@app.route('/api/lookup/<session_id>')
def get_lookup_status(session_id):
    """Get lookup status and results"""
    # Try database first
    conn = get_db_connection()
    db_session = conn.execute(
        'SELECT * FROM lookup_sessions WHERE session_id = ?', (session_id,)
    ).fetchone()
    conn.close()
    
    if db_session:
        session_data = dict(db_session)
        # Convert JSON strings back to objects
        if session_data['pdf_urls']:
            try:
                session_data['pdf_urls'] = json.loads(session_data['pdf_urls'])
            except:
                session_data['pdf_urls'] = []
        if session_data['tacoma_reports']:
            try:
                session_data['tacoma_reports'] = json.loads(session_data['tacoma_reports'])
            except:
                session_data['tacoma_reports'] = []
        
        return jsonify(session_data)
    
    # Fallback to memory storage
    if session_id not in lookup_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    return jsonify(lookup_sessions[session_id])

@app.route('/api/lookup/<session_id>/cancel', methods=['POST'])
def cancel_lookup(session_id):
    """Cancel a running lookup"""
    if session_id not in lookup_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    lookup_sessions[session_id]['status'] = 'cancelled'
    return jsonify({'status': 'cancelled'})

@app.route('/api/lookup/<session_id>/delete', methods=['DELETE'])
def delete_lookup(session_id):
    """Delete a lookup session"""
    try:
        # Delete from database
        conn = get_db_connection()
        cursor = conn.execute('DELETE FROM lookup_sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
        
        # Delete from memory storage if exists
        if session_id in lookup_sessions:
            del lookup_sessions[session_id]
        
        return jsonify({'status': 'deleted', 'message': 'Lookup deleted successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def run_lookup(session_id, address_line_1, city, zip_code, county):
    """Run the lookup process in a separate thread"""
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def async_lookup():
            lookup_tool = LookupTool()
            try:
                await lookup_tool.open_browser()
                
                # Parse address
                address_parts = address_line_1.split(" ")
                street_number = address_parts[0]
                street_name = address_parts[1]
                
                # Run address search
                await lookup_tool.address_search(street_number, street_name, county)
                
                # Get report PDFs
                pdf_urls = await lookup_tool.get_report_pdf()
                
                # Run tax rate lookup if city and zip provided
                location_code = None
                if city and zip_code:
                    location_code = await lookup_tool.tax_rate_lookup(address_line_1, city, zip_code)
                
                # Run Tacoma report lookup if county is Pierce
                tacoma_reports = []
                if county.lower() == 'pierce':
                    tacoma_reports = await lookup_tool.Tacoma_report_lookup(address_line_1)
                
                results = {
                    'pdf_urls': pdf_urls or [],
                    'location_code': location_code,
                    'tacoma_reports': tacoma_reports,
                    'completed_at': datetime.now().isoformat()
                }
                
                # Save to database
                conn = get_db_connection()
                conn.execute(
                    'UPDATE lookup_sessions SET status = ?, completed_at = ?, pdf_urls = ?, location_code = ?, tacoma_reports = ? WHERE session_id = ?',
                    ('completed', datetime.now().isoformat(), 
                     json.dumps(pdf_urls or []), location_code, 
                     json.dumps(tacoma_reports), session_id)
                )
                conn.commit()
                conn.close()
                
                # Update memory storage
                lookup_sessions[session_id]['results'] = results
                lookup_sessions[session_id]['status'] = 'completed'
                
            except Exception as e:
                error_msg = str(e)
                
                # Save error to database
                conn = get_db_connection()
                conn.execute(
                    'UPDATE lookup_sessions SET status = ?, error_message = ? WHERE session_id = ?',
                    ('error', error_msg, session_id)
                )
                conn.commit()
                conn.close()
                
                # Update memory storage
                lookup_sessions[session_id]['error'] = error_msg
                lookup_sessions[session_id]['status'] = 'error'
            finally:
                await lookup_tool.close_browser()
        
        loop.run_until_complete(async_lookup())
        loop.close()
        
    except Exception as e:
        lookup_sessions[session_id]['error'] = str(e)
        lookup_sessions[session_id]['status'] = 'error'

@app.route('/api/sessions')
def get_sessions():
    """Get all lookup sessions"""
    conn = get_db_connection()
    lookups = conn.execute(
        'SELECT * FROM lookup_sessions ORDER BY start_time DESC LIMIT 10'
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
        if session_data['tacoma_reports']:
            try:
                session_data['tacoma_reports'] = json.loads(session_data['tacoma_reports'])
            except:
                session_data['tacoma_reports'] = []
        sessions_list.append(session_data)
    
    return jsonify(sessions_list)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
