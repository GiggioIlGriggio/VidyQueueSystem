from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import time
from threading import Thread
import json
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-default-secret-key')  # More persistent secret key

# Data storage configuration
DATA_FOLDER = 'data'
COURTS_DATA_FILE = os.path.join(DATA_FOLDER, 'courts.json')

# Ensure the data directory exists
os.makedirs(DATA_FOLDER, exist_ok=True)

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
        
    return render_template('index.html', court_data=court_data)

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
        
    if 0 <= court_id < len(COURT_NAMES):
        court = court_system.courts[court_id]
        queue_data = [{'name': team['name'], 'time': team['time'], 'estimated_wait': team['estimated_wait']} 
                     for team in court.queue]
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
        court_system.save_to_json()

    def restore_state(self, index):
        """Restore queue state from history"""
        if 0 <= index < len(self.history):
            state = self.history[index]
            self.queue = state['queue'].copy()
            self.update_estimated_waits()
            
            # Persist data after state changes
            court_system.save_to_json()
            return True
        return False

    def add_team(self, team_name):
        """Add a team to the end of the queue."""
        self.queue.append({
            'name': team_name,
            'time': self.MATCH_DURATION if len(self.queue) == 0 else 0,  # First team gets match time, others wait
            'estimated_wait': self.calculate_estimated_wait(len(self.queue))
        })
        print(f"Team {team_name} added to {self.court_name} queue.")
        self.save_state(f"Added team: {team_name}")

    def calculate_estimated_wait(self, position):
        """Calculate estimated wait time for a team at a given position."""
        if position == 0:  # Currently playing team
            return 0
        elif position > len(self.queue):
            return 0
        
        wait_time = 0
        # Add remaining time of current playing team
        if self.queue and self.queue[0]['time'] > 0:
            wait_time += self.queue[0]['time']
        
        # Add full match duration for each team ahead
        wait_time += (position - 1) * self.MATCH_DURATION
        return wait_time

    def shift_queue(self):
        """Remove the team at the top of the queue and update remaining teams."""
        if self.queue:
            removed_team = self.queue.pop(0)
            print(f"Team {removed_team['name']} has been removed from {self.court_name} queue.")
            
            # Update remaining teams
            for i, team in enumerate(self.queue):
                if team['time'] == 0:  # If team was waiting
                    team['time'] = self.MATCH_DURATION  # Give them match time
                team['estimated_wait'] = self.calculate_estimated_wait(i)
            self.save_state(f"Shifted queue - Removed team: {removed_team['name']}")
        else:
            print(f"The {self.court_name} queue is empty.")

    def check_and_shift_queue(self):
        """Check the first team's time and shift the queue if necessary."""
        if self.queue and self.queue[0]['time'] <= 0:
            self.shift_queue()

    def update_estimated_waits(self):
        """Update estimated wait times for all teams in the queue."""
        for i, team in enumerate(self.queue):
            team['estimated_wait'] = self.calculate_estimated_wait(i)
            
    def start_timer(self):
        """Start the timer thread to decrement time for each team."""
        timer_thread = Thread(target=self.timer_loop)
        timer_thread.daemon = True  # Make thread daemon so it exits when main program exits
        timer_thread.start()

    def timer_loop(self):
        """Decrement time for each team every second."""
        while self.running:
            if self.queue:  # Only update if there are teams
                self.queue[0]['time'] -= 1  # Only decrement time for the playing team
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
        # Load data from JSON if exists, otherwise create new court systems
        if os.path.exists(COURTS_DATA_FILE):
            try:
                self.load_from_json()
            except Exception as e:
                print(f"Error loading court data: {e}")
                self.create_new_courts(court_names)
        else:
            self.create_new_courts(court_names)
            
    def create_new_courts(self, court_names):
        """Create new court systems with the given names"""
        self.courts = []
        for i, name in enumerate(court_names):
            self.courts.append(QueueSystem(i, name))
        
    def save_to_json(self):
        """Save court system state to JSON file"""
        try:
            court_data = []
            for court in self.courts:
                court_data.append(court.to_dict())
                
            with open(COURTS_DATA_FILE, 'w') as f:
                json.dump(court_data, f, indent=2)
                
            print(f"Court data saved to {COURTS_DATA_FILE}")
        except Exception as e:
            print(f"Error saving court data: {e}")
            
    def load_from_json(self):
        """Load court system state from JSON file"""
        try:
            with open(COURTS_DATA_FILE, 'r') as f:
                court_data = json.load(f)
                
            self.courts = []
            for data in court_data:
                self.courts.append(QueueSystem.from_dict(data))
                
            print(f"Court data loaded from {COURTS_DATA_FILE}")
        except Exception as e:
            print(f"Error loading court data: {e}")
            raise e

# Initialize the multi-court system
court_system = MultiCourtSystem(COURT_NAMES)

# Save data periodically
def periodic_save():
    """Save court system state to JSON file periodically"""
    while True:
        time.sleep(30)  # Save every 30 seconds
        court_system.save_to_json()

# Start periodic save in a background thread
periodic_save_thread = Thread(target=periodic_save)
periodic_save_thread.daemon = True
periodic_save_thread.start()

if __name__ == '__main__':
    print(f"Server running! Access locally at: http://127.0.0.1:5000")
    print(f"For access from other devices, use: http://<your-ip-address>:5000")
    print(f"To find your IP address, run 'ipconfig' on Windows or 'ifconfig' on Linux/Mac")
    app.run(host="0.0.0.0", port=5000, debug=False) 