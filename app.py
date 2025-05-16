from flask import Flask, render_template, request, jsonify, redirect, url_for
import datetime
import re
import json
import os
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini API
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

# Initialize the model
model = genai.GenerativeModel('gemini-1.5-pro')

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Google Calendar API configuration
CLIENT_SECRETS_FILE = 'client_secret.json'
REDIRECT_URI = 'http://localhost:5000/oauth2callback'
SCOPES = ['https://www.googleapis.com/auth/calendar']

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def get_calendar_service(credentials):
    """Build and return the Google Calendar service"""
    return build('calendar', 'v3', credentials=credentials)

def credentials_to_dict(credentials):
    """Convert credentials object to a dictionary"""
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

def parse_with_gemini(text):
    """Use Gemini to extract event details from natural language"""
    prompt = f"""
    Extract event details from the following text: "{text}"
    
    Please provide a structured JSON response with these fields:
    - title: The title or name of the event
    - start_date: The start date in YYYY-MM-DD format
    - start_time: The start time in HH:MM format (24-hour)
    - end_date: The end date in YYYY-MM-DD format (same as start_date if not specified)
    - end_time: The end time in HH:MM format (24-hour)
    - description: Additional details about the event
    - participants: List of people involved (empty list if none mentioned)
    - location: Location of the event (null if not specified)
    
    The current date is {datetime.datetime.now().strftime("%Y-%m-%d")}.
    """
    
    try:
        response = model.generate_content(prompt)
        # Extract JSON from response
        content = response.text
        # Find JSON content (may be wrapped in code blocks)
        json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = content
            
        # Clean up the string to ensure it's valid JSON
        json_str = re.sub(r'```.*?```', '', json_str, flags=re.DOTALL)
        
        # Parse JSON
        event_data = json.loads(json_str)
        return event_data
    except Exception as e:
        print(f"Error parsing with Gemini: {e}")
        # Fallback to basic parsing if Gemini fails
        return fallback_parsing(text)

def fallback_parsing(text):
    # Current date for reference
    now = datetime.datetime.now()
    
    # Default values
    title = "New Event"
    description = text
    date = now.date().strftime("%Y-%m-%d")
    start_time = "09:00"
    end_time = "10:00"
    
    # Try to extract title
    title_match = re.search(r'(meeting|appointment|call|event|conference|lunch|dinner) (with|about|on|for) (.+?)(?:\s+on\s+|\s+at\s+|$)', text, re.IGNORECASE)
    if title_match:
        title = title_match.group(0)
    
    return {
        "title": title,
        "start_date": date,
        "start_time": start_time,
        "end_date": date,
        "end_time": end_time,
        "description": description,
        "participants": [],
        "location": None
    }

def get_gemini_suggestions(query, events):
    events_context = "\n".join([
        f"Event: {e['summary']} on {e['start']['dateTime']}" 
        for e in events[:10]  # Limit to 10 events to avoid token limits
    ])
    
    prompt = f"""
    As Henry, a calendar assistant AI, respond to this user request:
    
    "{query}"
    
    Here are the user's upcoming calendar events:
    {events_context if events else "No upcoming events."}
    
    Provide a helpful, concise response addressing their query about their schedule.
    Keep your response under 150 words and focus on giving practical calendar advice.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error getting Gemini suggestions: {e}")
        return "I'm having trouble analyzing your schedule right now. Is there a specific event you'd like me to help with?"

@app.route('/')
def index():
    if 'credentials' not in request.cookies:
        return redirect(url_for('authorize'))
    return render_template('henry.html')

@app.route('/authorize')
def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI)
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true')
    
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI)
    
    flow.fetch_token(authorization_response=request.url)
    
    credentials = flow.credentials
    response = redirect(url_for('index'))
    response.set_cookie('credentials', json.dumps(credentials_to_dict(credentials)))
    return response

@app.route('/api/events', methods=['GET'])
def get_events():
    if 'credentials' not in request.cookies:
        return jsonify({"error": "Not authenticated"}), 401
    
    credentials = Credentials(**json.loads(request.cookies.get('credentials')))
    
    try:
        service = get_calendar_service(credentials)
        
        # Get current week start and end
        now = datetime.datetime.utcnow()
        start_of_week = now - datetime.timedelta(days=now.weekday())
        end_of_week = start_of_week + datetime.timedelta(days=7)
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_week.isoformat() + 'Z',
            timeMax=end_of_week.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        return jsonify(events)
    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/events', methods=['POST'])
def create_event():
    if 'credentials' not in request.cookies:
        return jsonify({"error": "Not authenticated"}), 401
    
    credentials = Credentials(**json.loads(request.cookies.get('credentials')))
    data = request.json
    text = data.get('text', '')
    
    try:
        # Use Gemini to parse the event details
        event_data = parse_with_gemini(text)
        
        # Create event object for Google Calendar
        start_datetime = f"{event_data['start_date']}T{event_data['start_time']}:00"
        end_datetime = f"{event_data['end_date']}T{event_data['end_time']}:00"
        
        event = {
            'summary': event_data['title'],
            'location': event_data['location'],
            'description': event_data['description'],
            'start': {
                'dateTime': start_datetime,
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_datetime,
                'timeZone': 'UTC',
            },
            'attendees': [{'email': email} for email in event_data['participants']],
            'reminders': {
                'useDefault': True,
            },
        }
        
        service = get_calendar_service(credentials)
        created_event = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()
        
        return jsonify({"success": True, "event": created_event})
    except Exception as e:
        print(f"Error creating event: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/events/<string:event_id>', methods=['DELETE'])
def delete_event(event_id):
    if 'credentials' not in request.cookies:
        return jsonify({"error": "Not authenticated"}), 401
    
    credentials = Credentials(**json.loads(request.cookies.get('credentials')))
    
    try:
        service = get_calendar_service(credentials)
        service.events().delete(
            calendarId='primary',
            eventId=event_id
        ).execute()
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting event: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ask', methods=['POST'])
def ask_assistant():
    if 'credentials' not in request.cookies:
        return jsonify({"error": "Not authenticated"}), 401
    
    credentials = Credentials(**json.loads(request.cookies.get('credentials')))
    data = request.json
    query = data.get('query', '')
    
    try:
        service = get_calendar_service(credentials)
        
        # Get events for the next 7 days
        now = datetime.datetime.utcnow()
        end_date = now + datetime.timedelta(days=7)
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat() + 'Z',
            timeMax=end_date.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        response = get_gemini_suggestions(query, events)
        return jsonify({"response": response})
    except Exception as e:
        print(f"Error getting suggestions: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Only for development
    app.run(debug=True)
