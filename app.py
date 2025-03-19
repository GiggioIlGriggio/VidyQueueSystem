from flask import Flask, render_template, request, redirect, url_for, jsonify, session, make_response
import time
from threading import Thread
import json
from datetime import datetime, timedelta
import os
from pymongo import MongoClient
from bson.objectid import ObjectId
import urllib.parse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-default-secret-key')  # More persistent secret key

# MongoDB configuration
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
print(f"Loaded MONGO_URI from environment: '{MONGO_URI[:10]}...' (showing first 10 chars for security)")

# Validate the MongoDB URI format
if not MONGO_URI.startswith('mongodb://') and not MONGO_URI.startswith('mongodb+srv://'):
    print(f"ERROR: Invalid MongoDB URI format: '{MONGO_URI[:10]}...' (showing first 10 chars for security)")
    print("Environment variables available: ", list(os.environ.keys()))
    print("The URI must begin with 'mongodb://' or 'mongodb+srv://'")
    print("Please check your environment variables in the Render dashboard.")
    
    # Hard-code the MongoDB URI as a fallback for production
    if os.environ.get('FLASK_ENV') == 'production':
        print("Using hardcoded MongoDB URI as fallback")
        # NOTE: You need to replace the YOUR_ACTUAL_PASSWORD placeholder with your real password
        MONGO_URI = "mongodb+srv://user:YOUR_ACTUAL_PASSWORD@clustersanndmatch.kvu15.mongodb.net/?retryWrites=true&w=majority&appName=ClusterSanndMatch"
        if MONGO_URI.find("YOUR_ACTUAL_PASSWORD") != -1:
            print("WARNING: You need to edit app.py and replace YOUR_ACTUAL_PASSWORD with your real MongoDB password!")
    else:
        # Use a fallback for local development
        print("Using fallback local MongoDB for development")
        MONGO_URI = 'mongodb://localhost:27017/'

try:
    # URL encode the password in the connection string if it contains special characters
    if '@' in MONGO_URI:
        # Split the URI into parts before and after the @ symbol
        prefix, suffix = MONGO_URI.split('@', 1)
        if ':' in prefix:
            # Split the prefix into username and password
            username, password = prefix.split(':', 1)
            # URL encode the password
            encoded_password = urllib.parse.quote_plus(password)
            # Reconstruct the URI with encoded password
            MONGO_URI = f"{username}:{encoded_password}@{suffix}"
    
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # Test the connection
    mongo_client.server_info()
    print("Successfully connected to MongoDB")
    
    db = mongo_client['beachrank']
    courts_collection = db['courts']
    
    # Ensure the courts collection has an index on court_id for faster lookups
    courts_collection.create_index('court_id')
except Exception as e:
    print(f"Error connecting to MongoDB: {str(e)}")
    print("Please check your MONGO_URI environment variable and ensure it's properly configured.")
    print("Example format: mongodb+srv://username:password@cluster.mongodb.net/dbname?retryWrites=true&w=majority")
    raise

# Translation files
TRANSLATIONS_DIR = os.path.join('static', 'translations')
AVAILABLE_LANGUAGES = ['en', 'fr']
DEFAULT_LANGUAGE = 'en'

# Load translations
def load_translations():
    translations = {}
    for lang in AVAILABLE_LANGUAGES:
        with open(os.path.join(TRANSLATIONS_DIR, f'{lang}.json'), 'r', encoding='utf-8') as f:
            translations[lang] = json.load(f)
    return translations

# Global translations dictionary
translations = load_translations()

# Admin credentials (in a real app, these would be stored securely in a database)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"  # In production, use a secure password hash

# Court configurations
COURT_NAMES = ["Court 1", "Court 2", "Court 3", "Court 4"]
COURT_COLORS = ["#FF6B6B", "#4ECDC4", "#FFD166", "#6A0572"]  # Colors for each court
COURT_ICONS = ["volleyball-ball", "umbrella-beach", "sun", "water"]  # Icons for each court

# Before each request, check language settings
@app.before_request
def before_request():
    # Set default language if not already set
    if 'language' not in session:
        session['language'] = DEFAULT_LANGUAGE
    
    # Handle language change request from URL query parameter
    if request.args.get('lang') in AVAILABLE_LANGUAGES:
        session['language'] = request.args.get('lang')
        
    # Handle language change request from form data
    if request.method == 'POST' and request.form.get('lang') in AVAILABLE_LANGUAGES:
        session['language'] = request.form.get('lang')

# Helper function to get text in the current language
def get_text(key_path):
    lang = session.get('language', DEFAULT_LANGUAGE)
    keys = key_path.split('.')
    
    # Navigate through nested dictionary
    data = translations.get(lang, translations[DEFAULT_LANGUAGE])
    for key in keys:
        if key in data:
            data = data[key]
        else:
            # Fall back to English if key not found
            data = translations[DEFAULT_LANGUAGE]
            for k in keys:
                if k in data:
                    data = data[k]
                else:
                    return key_path  # Return the key path if not found
    
    return data

# Add translation helper to Jinja2 environment
@app.context_processor
def inject_helpers():
    return {
        'get_text': get_text,
        'current_language': lambda: session.get('language', DEFAULT_LANGUAGE),
        'available_languages': AVAILABLE_LANGUAGES
    }

def login_required(f):
    """Decorator to require login for admin routes"""
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for_with_lang('admin_login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Route for admin login
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    # Check for language parameter and update it in the URL if needed
    if request.method == 'GET':
        lang = request.args.get('lang')
        if lang in AVAILABLE_LANGUAGES:
            if lang != session.get('language'):
                session['language'] = lang
                # Redirect to the same page with updated language parameter
                return redirect(url_for_with_lang('admin_login'))
        elif session.get('language') != DEFAULT_LANGUAGE:
            # Redirect to include the language parameter in URL
            return redirect(url_for_with_lang('admin_login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Handle language from form
        lang = request.form.get('lang')
        if lang in AVAILABLE_LANGUAGES:
            session['language'] = lang
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for_with_lang('admin_dashboard'))
        else:
            return render_template('admin_login.html', error="Invalid credentials")
    
    return render_template('admin_login.html')

# Route for admin logout
@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    return redirect(url_for_with_lang('home'))

# Route for admin dashboard
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    # Check for language parameter and update it in the URL if needed
    lang = request.args.get('lang')
    if lang in AVAILABLE_LANGUAGES:
        if lang != session.get('language'):
            session['language'] = lang
            # Redirect to the same page with updated language parameter
            return redirect(url_for_with_lang('admin_dashboard'))
    elif session.get('language') != DEFAULT_LANGUAGE:
        # Redirect to include the language parameter in URL
        return redirect(url_for_with_lang('admin_dashboard'))
    
    court_data = []
    for court_id in range(len(COURT_NAMES)):
        queue = court_system.courts[court_id].queue
        queue_data = [{'name': team['name'], 'time': team['time'], 'estimated_wait': team['estimated_wait']} 
                     for team in queue]
        court_data.append({
            'id': court_id,
            'name': COURT_NAMES[court_id],
            'color': COURT_COLORS[court_id],
            'icon': COURT_ICONS[court_id],
            'queue': queue_data
        })
    return render_template('admin_dashboard.html', court_data=court_data)

# Route for admin history page
@app.route('/admin/history/<int:court_id>')
@login_required
def admin_history(court_id):
    # Check for language parameter and update it in the URL if needed
    lang = request.args.get('lang')
    if lang in AVAILABLE_LANGUAGES:
        if lang != session.get('language'):
            session['language'] = lang
            # Redirect to the same page with updated language parameter
            return redirect(url_for_with_lang('admin_history', court_id=court_id))
    elif session.get('language') != DEFAULT_LANGUAGE:
        # Redirect to include the language parameter in URL
        return redirect(url_for_with_lang('admin_history', court_id=court_id))
    
    if 0 <= court_id < len(COURT_NAMES):
        return render_template('admin_history.html', 
                              history=court_system.courts[court_id].history,
                              court_id=court_id, 
                              court_name=COURT_NAMES[court_id],
                              court_color=COURT_COLORS[court_id])
    return redirect(url_for_with_lang('admin_dashboard'))

# Route to restore queue state
@app.route('/admin/restore/<int:court_id>/<int:index>', methods=['POST'])
@login_required
def restore_queue(court_id, index):
    if 0 <= court_id < len(COURT_NAMES) and 0 <= index < len(court_system.courts[court_id].history):
        court_system.courts[court_id].restore_state(index)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid history index or court ID'}), 400

# Route for the home page - shows all courts overview
@app.route('/')
def home():
    # Check for language parameter and update it in the URL if needed
    lang = request.args.get('lang')
    if lang in AVAILABLE_LANGUAGES:
        if lang != session.get('language'):
            session['language'] = lang
            # Redirect to the same page with updated language parameter
            return redirect(url_for_with_lang('home'))
    elif session.get('language') != DEFAULT_LANGUAGE:
        # Redirect to include the language parameter in URL
        return redirect(url_for_with_lang('home'))
    
    # Check for updates to the file from other processes
    court_system.check_for_file_updates()
        
    court_data = []
    for court_id in range(len(COURT_NAMES)):
        court = court_system.courts[court_id]
        currently_playing = None
        waiting_count = 0
        
        if court.queue:
            currently_playing = court.queue[0]['name']
            waiting_count = len(court.queue) - 1
            
        court_data.append({
            'id': court_id,
            'name': COURT_NAMES[court_id],
            'color': COURT_COLORS[court_id],
            'icon': COURT_ICONS[court_id],
            'currently_playing': currently_playing,
            'waiting_count': waiting_count
        })
    
    response = make_response(render_template('index.html', court_data=court_data))
    # Add cache control headers to prevent browser caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Route for viewing a specific court
@app.route('/court/<int:court_id>')
def view_court(court_id):
    # Check for language parameter and update it in the URL if needed
    lang = request.args.get('lang')
    if lang in AVAILABLE_LANGUAGES:
        if lang != session.get('language'):
            session['language'] = lang
            # Redirect to the same page with updated language parameter
            return redirect(url_for_with_lang('view_court', court_id=court_id))
    elif session.get('language') != DEFAULT_LANGUAGE:
        # Redirect to include the language parameter in URL
        return redirect(url_for_with_lang('view_court', court_id=court_id))
    
    if 0 <= court_id < len(COURT_NAMES):
        court = court_system.courts[court_id]
        queue_data = [{'name': team['name'], 'time': team['time'], 'estimated_wait': team['estimated_wait']} 
                     for team in court.queue]
                     
        # Add start timestamp for the first team if available
        if queue_data and len(court.queue) > 0 and 'start_timestamp' in court.queue[0] and court.queue[0]['start_timestamp']:
            queue_data[0]['start_timestamp'] = court.queue[0]['start_timestamp']
            # Add server current timestamp for time synchronization
            queue_data[0]['server_time'] = datetime.now().timestamp()
            
        for team in queue_data:
            team['time_str'] = f"{team['time'] // 60}:{team['time'] % 60:02d}"
            team['wait_str'] = f"{team['estimated_wait'] // 60}:{team['estimated_wait'] % 60:02d}"
            
        # Get translated text for JavaScript usage
        translations_for_js = {
            'playing': get_text('court.playing'),
            'waiting': get_text('court.waiting'),
            'wait': get_text('court.wait'),
            'none_playing': get_text('court.none_playing')
        }
            
        return render_template('court.html', 
                               court_id=court_id,
                               court_name=COURT_NAMES[court_id],
                               court_color=COURT_COLORS[court_id],
                               court_icon=COURT_ICONS[court_id],
                               court=court,
                               queue_data=queue_data,
                               translations_js=translations_for_js)
    return redirect(url_for_with_lang('home'))

# Route for team registration to a specific court
@app.route('/register/<int:court_id>', methods=['POST'])
def register_team(court_id):
    if 0 <= court_id < len(COURT_NAMES):
        team_name = request.form.get('team-name')
        if team_name:
            court_system.courts[court_id].add_team(team_name)
        
        # Check for language parameter
        lang = request.form.get('lang')
        if lang in AVAILABLE_LANGUAGES:
            session['language'] = lang
            
        return redirect(url_for_with_lang('view_court', court_id=court_id))
    return redirect(url_for_with_lang('home'))

# Route to shift the queue for a specific court
@app.route('/shift_queue/<int:court_id>', methods=['POST'])
def shift_queue(court_id):
    if 0 <= court_id < len(COURT_NAMES):
        court_system.courts[court_id].shift_queue()
    
    # Check for language parameter
    lang = request.form.get('lang')
    if lang in AVAILABLE_LANGUAGES:
        session['language'] = lang
        
    # Determine where to redirect based on referrer
    referrer = request.referrer
    if referrer and '/admin/' in referrer:
        return redirect(url_for_with_lang('admin_dashboard'))
    return redirect(url_for_with_lang('view_court', court_id=court_id))

# Route to check and shift the queue for a specific court
@app.route('/check_queue/<int:court_id>', methods=['POST'])
def check_queue(court_id):
    if 0 <= court_id < len(COURT_NAMES):
        court_system.courts[court_id].check_and_shift_queue()
    return '', 204  # No content response

# Route to get queue data for a specific court
@app.route('/queue_data/<int:court_id>')
def get_queue_data(court_id):
    # Handle language parameter if present
    if request.args.get('lang') in AVAILABLE_LANGUAGES:
        session['language'] = request.args.get('lang')
    
    # Check for updates to the file from other processes
    court_system.check_for_file_updates()
        
    if 0 <= court_id < len(COURT_NAMES):
        court = court_system.courts[court_id]
        queue_data = [{'name': team['name'], 'time': team['time'], 'estimated_wait': team['estimated_wait']} 
                     for team in court.queue]
                     
        # Add start timestamp for the first team if available
        if queue_data and len(court.queue) > 0 and 'start_timestamp' in court.queue[0] and court.queue[0]['start_timestamp']:
            queue_data[0]['start_timestamp'] = court.queue[0]['start_timestamp']
            # Add server current timestamp for time synchronization
            queue_data[0]['server_time'] = datetime.now().timestamp()
            
        for team in queue_data:
            team['time_str'] = f"{team['time'] // 60}:{team['time'] % 60:02d}"
            team['wait_str'] = f"{team['estimated_wait'] // 60}:{team['estimated_wait'] % 60:02d}"
        
        # Get translations for JavaScript usage
        translations_for_js = {
            'playing': get_text('court.playing'),
            'waiting': get_text('court.waiting'),
            'wait': get_text('court.wait'),
            'none_playing': get_text('court.none_playing')
        }
        
        # Include current language and translations in response
        response_data = {
            'queue': queue_data,
            'current_language': session.get('language', DEFAULT_LANGUAGE),
            'translations': translations_for_js
        }
        return jsonify(response_data)
    
    return jsonify({
        'queue': [], 
        'current_language': session.get('language', DEFAULT_LANGUAGE),
        'translations': {
            'playing': get_text('court.playing'),
            'waiting': get_text('court.waiting'),
            'wait': get_text('court.wait'),
            'none_playing': get_text('court.none_playing')
        }
    })

# Route to delete a team from a specific court
@app.route('/delete_team/<int:court_id>/<int:index>', methods=['POST'])
def delete_team(court_id, index):
    if 0 <= court_id < len(COURT_NAMES) and court_system.courts[court_id].queue and 0 <= index < len(court_system.courts[court_id].queue):
        deleted_team = court_system.courts[court_id].delete_team(index)
        
        # Check for language parameter in the query string
        lang = request.args.get('lang')
        if lang in AVAILABLE_LANGUAGES:
            session['language'] = lang
            
        return jsonify({'success': True, 'deleted_team': deleted_team})
    return jsonify({'success': False, 'error': 'Invalid team index or court ID'}), 400

# Route to set language from form submission
@app.route('/set_language', methods=['POST'])
def set_language():
    """Handle language changes from form submissions"""
    if request.form.get('lang') in AVAILABLE_LANGUAGES:
        session['language'] = request.form.get('lang')
    
    # Redirect back to the page that submitted the form
    redirect_url = request.form.get('redirect_url', '/')
    return redirect(redirect_url)

# Helper function to add language to url_for
def url_for_with_lang(*args, **kwargs):
    """Add the current language as a parameter to url_for"""
    lang = session.get('language', DEFAULT_LANGUAGE)
    kwargs['lang'] = lang
    return url_for(*args, **kwargs)

# Route to get courts data for homepage
@app.route('/courts_data')
def get_courts_data():
    # Handle language parameter if present
    if request.args.get('lang') in AVAILABLE_LANGUAGES:
        session['language'] = request.args.get('lang')
    
    # Check for updates to the file from other processes
    court_system.check_for_file_updates()
        
    court_data = []
    for court_id in range(len(COURT_NAMES)):
        court = court_system.courts[court_id]
        currently_playing = None
        waiting_count = 0
        
        if court.queue:
            currently_playing = court.queue[0]['name']
            waiting_count = len(court.queue) - 1
            
        court_data.append({
            'id': court_id,
            'name': COURT_NAMES[court_id],
            'color': COURT_COLORS[court_id],
            'icon': COURT_ICONS[court_id],
            'currently_playing': currently_playing,
            'waiting_count': waiting_count
        })
    
    return jsonify({
        'court_data': court_data,
        'current_language': session.get('language', DEFAULT_LANGUAGE)
    })

# Route for health checking
@app.route('/health')
def health_check():
    storage_info = {
        'database_type': 'MongoDB Atlas',
        'database_name': db.name,
        'connected': mongo_client.server_info() is not None,
        'courts_count': courts_collection.count_documents({}),
        'environment': os.environ.get('FLASK_ENV', 'development')
    }
    return jsonify(storage_info)

# Route to check environment variables (for debugging)
@app.route('/debug/env')
@login_required
def debug_env():
    # Only show this in development or when explicitly allowed
    if os.environ.get('FLASK_ENV') != 'production' or os.environ.get('ALLOW_ENV_DEBUG') == 'true':
        env_dict = {}
        for key, value in os.environ.items():
            # Mask sensitive values
            if any(sensitive in key.lower() for sensitive in ['pass', 'secret', 'key', 'token', 'auth']):
                env_dict[key] = value[:3] + '****' if value else None
            else:
                env_dict[key] = value
                
        return jsonify({
            'environment_variables': env_dict,
            'mongo_uri_valid_format': MONGO_URI.startswith('mongodb://') or MONGO_URI.startswith('mongodb+srv://'),
            'mongo_uri_prefix': MONGO_URI[:10] + '...' if MONGO_URI else None
        })
    return jsonify({'error': 'Debug endpoints are disabled in production'}), 403

class QueueSystem:
    def __init__(self, court_id, court_name):
        self.court_id = court_id
        self.court_name = court_name
        self.queue = []
        self.running = True
        self.MATCH_DURATION = 900  # 15 minutes in seconds
        self.history = []  # List to store queue history
        self.start_timer()

    def save_state(self, action):
        """Save current queue state to history"""
        state = {
            'timestamp': datetime.now().isoformat(),
            'queue': self.queue.copy(),
            'action': action
        }
        self.history.append(state)
        
        # Persist data after state changes
        court_system.save_to_mongodb()

    def restore_state(self, index):
        """Restore queue state from history"""
        if 0 <= index < len(self.history):
            state = self.history[index]
            self.queue = state['queue'].copy()
            
            # If there's a playing team, update its start_timestamp to now
            if self.queue and 'time' in self.queue[0]:
                current_time = self.queue[0]['time']
                # Calculate a timestamp that makes the remaining time correct
                self.queue[0]['start_timestamp'] = datetime.now().timestamp() - (self.MATCH_DURATION - current_time)
            
            self.update_estimated_waits()
            
            # Persist data after state changes
            court_system.save_to_mongodb()
            return True
        return False

    def add_team(self, team_name):
        """Add a team to the end of the queue."""
        current_time = datetime.now().timestamp()
        
        if len(self.queue) == 0:
            # First team gets match time and a start timestamp
            self.queue.append({
                'name': team_name,
                'time': self.MATCH_DURATION,
                'estimated_wait': self.calculate_estimated_wait(len(self.queue)),
                'start_timestamp': current_time  # Time when the team started playing
            })
        else:
            # Other teams wait and don't have a start timestamp yet
            self.queue.append({
                'name': team_name,
                'time': 0,
                'estimated_wait': self.calculate_estimated_wait(len(self.queue)),
                'start_timestamp': None
            })
            
        print(f"Team {team_name} added to {self.court_name} queue.")
        self.save_state(f"Added team: {team_name}")

    def calculate_estimated_wait(self, position):
        """Calculate the estimated wait time for a team at the given position."""
        if position <= 0:
            return 0
        
        # Calculate wait time based on the current team's remaining time
        wait_time = 0
        if self.queue and position > 0:
            if 'start_timestamp' in self.queue[0] and self.queue[0]['start_timestamp']:
                # Calculate time remaining for current team using timestamp
                elapsed = datetime.now().timestamp() - self.queue[0]['start_timestamp']
                remaining = max(0, self.MATCH_DURATION - elapsed)
                wait_time = remaining
            else:
                # Fall back to the time field if timestamp not available
                wait_time = self.queue[0]['time']
                
        # Add match duration for each team ahead in the queue (excluding the currently playing team)
        wait_time += (position - 1) * self.MATCH_DURATION
        
        return int(wait_time)

    def shift_queue(self):
        """Remove the first team from the queue and shift everyone up."""
        if self.queue:
            removed_team = self.queue.pop(0)
            
            # If there's a next team to play, set its initial time and start timestamp
            if self.queue:
                self.queue[0]['time'] = self.MATCH_DURATION
                self.queue[0]['start_timestamp'] = datetime.now().timestamp()
                
            self.update_estimated_waits()
            self.save_state(f"Shifted queue - Removed team: {removed_team['name']}")
            # Force save to JSON immediately to ensure persistence
            court_system.save_to_mongodb()
            return removed_team
        return None

    def check_and_shift_queue(self):
        """Check the first team's time and shift the queue if necessary."""
        if self.queue and self.queue[0]['time'] <= 0:
            self.shift_queue()
            # Force save to JSON immediately to ensure persistence
            court_system.save_to_mongodb()

    def update_estimated_waits(self):
        """Update the estimated wait times for all teams in the queue."""
        for i in range(1, len(self.queue)):
            self.queue[i]['estimated_wait'] = self.calculate_estimated_wait(i)
            
    def start_timer(self):
        """Start the timer thread to decrement time for each team."""
        timer_thread = Thread(target=self.timer_loop)
        timer_thread.daemon = True  # Make thread daemon so it exits when main program exits
        timer_thread.start()

    def timer_loop(self):
        """Decrement time for each team every second."""
        while self.running:
            if self.queue:  # Only update if there are teams
                # Only update time for the playing team
                if 'start_timestamp' in self.queue[0] and self.queue[0]['start_timestamp']:
                    # Calculate time remaining based on timestamp
                    elapsed = datetime.now().timestamp() - self.queue[0]['start_timestamp']
                    self.queue[0]['time'] = max(0, int(self.MATCH_DURATION - elapsed))
                else:
                    # Fallback to traditional timer
                    self.queue[0]['time'] -= 1
                    
                self.update_estimated_waits()  # Update wait times
                self.check_and_shift_queue()
            time.sleep(1)

    def stop_timer(self):
        """Stop the timer thread."""
        self.running = False

    def delete_team(self, index):
        """Delete a team from the queue at the specified index."""
        if 0 <= index < len(self.queue):
            deleted_team = self.queue.pop(index)
            self.update_estimated_waits()
            self.save_state(f"Deleted team: {deleted_team['name']}")
            # Force save to JSON immediately to ensure persistence
            court_system.save_to_mongodb()
            return deleted_team
        return None
        
    def to_dict(self):
        """Convert queue system state to dictionary for JSON serialization"""
        return {
            'court_id': self.court_id,
            'court_name': self.court_name,
            'queue': self.queue,
            'history': self.history,
            'match_duration': self.MATCH_DURATION
        }
        
    @classmethod
    def from_dict(cls, data):
        """Create a QueueSystem instance from a dictionary"""
        court_system = cls(data['court_id'], data['court_name'])
        court_system.queue = data['queue']
        court_system.history = data['history']
        court_system.MATCH_DURATION = data['match_duration']
        court_system.update_estimated_waits()
        return court_system

class MultiCourtSystem:
    def __init__(self, court_names):
        self.courts = []
        # Try to load courts from MongoDB
        if courts_collection.count_documents({}) > 0:
            try:
                self.load_from_mongodb()
            except Exception as e:
                print(f"Error loading court data from MongoDB: {e}")
                self.create_new_courts(court_names)
        else:
            self.create_new_courts(court_names)
            
    def create_new_courts(self, court_names):
        """Create new court systems with the given names"""
        self.courts = []
        for i, name in enumerate(court_names):
            self.courts.append(QueueSystem(i, name))
        # Save new courts to MongoDB
        self.save_to_mongodb()
    
    def check_for_file_updates(self):
        """Legacy method - MongoDB handles this automatically now"""
        # No need to check for file updates with MongoDB
        return False
        
    def save_to_mongodb(self):
        """Save court system state to MongoDB"""
        try:
            # Clear existing court data
            courts_collection.delete_many({})
            
            # Insert new court data
            for court in self.courts:
                court_data = court.to_dict()
                courts_collection.insert_one(court_data)
            
            print(f"Court data saved to MongoDB, collection: {courts_collection.name}")
        except Exception as e:
            print(f"Error saving court data to MongoDB: {e}")
            
    def save_to_json(self):
        """Legacy method kept for backward compatibility - redirects to MongoDB save"""
        self.save_to_mongodb()
            
    def load_from_mongodb(self):
        """Load court system state from MongoDB"""
        try:
            # Get all courts from MongoDB
            court_data = list(courts_collection.find({}))
            
            self.courts = []
            for data in court_data:
                # Remove MongoDB _id field before creating QueueSystem
                if '_id' in data:
                    del data['_id']
                self.courts.append(QueueSystem.from_dict(data))
            
            print(f"Court data loaded from MongoDB, collection: {courts_collection.name}")
        except Exception as e:
            print(f"Error loading court data from MongoDB: {e}")
            raise e
            
    def load_from_json(self):
        """Legacy method kept for backward compatibility - redirects to MongoDB load"""
        self.load_from_mongodb()

# Initialize the multi-court system
court_system = MultiCourtSystem(COURT_NAMES)

# Save data periodically
def periodic_save():
    """Save court system state to MongoDB periodically"""
    while True:
        time.sleep(10)  # Save every 10 seconds
        court_system.save_to_mongodb()

# Start periodic save in a background thread
periodic_save_thread = Thread(target=periodic_save)
periodic_save_thread.daemon = True
periodic_save_thread.start()

if __name__ == '__main__':
    print(f"Server running! Access locally at: http://127.0.0.1:5000")
    print(f"For access from other devices, use: http://<your-ip-address>:5000")
    print(f"To find your IP address, run 'ipconfig' on Windows or 'ifconfig' on Linux/Mac")
    app.run(host="0.0.0.0", port=5000, debug=False) 