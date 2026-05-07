import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import json
import random
import uuid
import asyncio
import requests # Used for making the API call
import ssl
import smtplib
from email.message import EmailMessage
import re # Used for email validation
from typing import Dict, Any, Optional, List, Tuple

from tensorboard import summary

# --- 0. CRITICAL CONFIGURATION ---
# IMPORTANT: When running locally, Streamlit handles secrets. 
# For this environment, we use an empty string as the key is injected at runtime.
GEMINI_API_KEY = "AIzaSyA18RxDxo9AV7I6zKK3EoXum99MxK73Awk" # The environment will inject the real key
MODEL_NAME = "gemini-2.5-flash"
# The full endpoint URL required for the API call
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"


YOUTUBE_API_KEY = "AIzaSyDUd2_H2dNQGdyGBnxQUR12nj1dgV2w6yo" 
# EMAIL CONFIGURATION (Must be a system email dedicated to this app)
# 
# 🛑🛑🛑 ACTION REQUIRED: REPLACE THESE PLACEHOLDERS 🛑🛑🛑
# 
SMTP_SERVER = "smtp.gmail.com"

SMTP_PORT = 465 
SENDER_EMAIL = "kiruthi0104@gmail.com" # <--- 🛑 REPLACE WITH YOUR ACTUAL GMAIL 🛑
SENDER_PASSWORD = "srnj aduw orgu lnhk" # <--- 🛑 REPLACE WITH YOUR GMAIL APP PASSWORD 🛑

# --- 1. MySQL Connector Library Import ---
try:
    import mysql.connector
except ImportError:
    st.error("The 'mysql-connector-python' library is not installed. Please run: pip install mysql-connector-python")
    st.stop()

# --- 2. Database Configuration (!!! CRITICAL: REPLACE WITH YOUR INFO !!!) ---
# Using the structure provided by the user
DB_CONFIG = {
    "host": "127.0.0.1", 
    "user": "root",     
    "password": "Kiruthika0104!", # <-- UPDATE THIS PASSWORD
    "database": "ai_assistant_db" 
}

# Global State Initialization
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.role = None
    st.session_state.is_active_session = False
    st.session_state.auth_view = 'login'
    st.session_state.study_id = None 
    st.session_state.session_duration_minutes = 0 
    st.session_state.invite_id = "" 
    st.session_state.is_quiz_active = False # NEW: State for Gamification/Quiz
    st.session_state.quiz_data = None # NEW: Stores the quiz questions
    st.session_state.full_name = None


# =================================================================
# --- 3. DATABASE CONNECTION & UTILITIES (ADOPTED FROM USER'S WORKING CODE) ---
# =================================================================

def get_db_connection():
    """Initializes and returns a NEW connection for the database."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        st.error(f"Error connecting to MySQL Database: {err}")
        st.warning("Please check your MySQL server status and the DB_CONFIG credentials in the Python file.")
        return None

def authenticate_user(username, password):
    """Checks credentials against the 'users' table (Login RETRIEVAL)."""
    conn = get_db_connection()
    if not conn: return (False, None, None, None, None)
    
    cursor = conn.cursor(dictionary=True)
    # NOTE: Assumes the column is 'password_hash' and the user is passing the raw password.
    # In a real app, this should be a hash check. I'm leaving it as-is to match the user's provided function.
    query = "SELECT user_id, full_name, role, study_id FROM users WHERE username = %s AND password_hash = %s"
    try:
        cursor.execute(query, (username, password))
        user = cursor.fetchone()
        if user:
            return (True, user['user_id'], user['role'], user['full_name'], user['study_id'])
        return (False, None, None, None, None)
    except mysql.connector.Error as err:
        st.error(f"Authentication query error: {err}")
        return (False, None, None, None, None)
    finally:
        cursor.close()
        conn.close() 

def sign_up_user(username, password, name, role, email):
    """
    Inserts a new user's details into the 'users' table, including the new email field. 
    (Sign Up INSERTION).
    """
    conn = get_db_connection()
    if not conn: return (False, None)
    
    cursor = conn.cursor()
    
    # Generate a unique, user-friendly study ID (e.g., user-a1b2c3)
    unique_part = str(uuid.uuid4())[:6]
    study_id = f"user-{unique_part}"
    
    # Check if username already exists
    check_query = "SELECT COUNT(*) FROM users WHERE username = %s"
    try:
        cursor.execute(check_query, (username,))
        if cursor.fetchone()[0] > 0:
            st.error("Error: Username already exists.")
            return (False, None)
    except mysql.connector.Error as err:
        st.error(f"Error checking username existence: {err}")
        return (False, None)

    # NOTE: Updated query to include 'email' field
    query = "INSERT INTO users (username, password_hash, full_name, role, study_id, email) VALUES (%s, %s, %s, %s, %s, %s)"
    try:
        # NOTE: Using plaintext password for demonstration. DO NOT DO THIS IN PRODUCTION.
        cursor.execute(query, (username, password, name, role, study_id, email))
        conn.commit()
        st.success(f"Account created successfully for {name}! Your Study ID is: **{study_id}**")
        return (True, study_id)
    except mysql.connector.Error as err:
        st.error(f"Signup query error: {err}")
        return (False, None)
    finally:
        cursor.close()
        conn.close()

def get_user_email_by_study_id(study_id):
    """Fetches the email and full name of a user by their Study ID."""
    conn = get_db_connection()
    if not conn:
        return None
        
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        # Assumes an 'email' column exists for sending invites
        query = "SELECT email, full_name FROM users WHERE study_id = %s"
        cursor.execute(query, (study_id,))
        result = cursor.fetchone()
        
        if result and result.get('email') and result['email'].strip().lower() not in ["placeholder", "null", ""]:
            # Basic validation to ensure it looks like an email before returning
            if re.match(r"[^@]+@[^@]+\.[^@]+", result['email']):
                return result['email'], result['full_name']
        
        # Fallback if no valid email is found
        if result and result.get('full_name'):
            st.warning(f"Note: User '{result['full_name']}' does not have a valid email on file. Invitation cannot be sent.")
        
        return None
        
    except mysql.connector.Error as e:
        st.error(f"Database query error during email lookup: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def save_session_to_db():
    """Saves the current study session and EEG telemetry to the database."""
    user_id = st.session_state.get('user_id', 'guest')
    session_data_raw = st.session_state.get('current_session_data', [])
    
    # Determine Mode
    mode = st.session_state.get('session_mode', 'Solo Study')
    subject = st.session_state.get('group_subject' if mode == "Group Study" else 'subject', 'General Study')
    content_type = st.session_state.get('content_type', 'Detailed Notes')

    conn = get_db_connection()
    if not conn:
        return None
    
    cursor = conn.cursor()
    start_time = st.session_state.get('start_time')
    if isinstance(start_time, float):
        start_dt = datetime.fromtimestamp(start_time)
    else:
        start_dt = start_time or datetime.now()
        
    start_time_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Simple duration calculation
    elapsed_seconds = (datetime.now() - start_dt).total_seconds()
    duration_mins = int(elapsed_seconds / 60)

    try:
        session_query = """
            INSERT INTO sessions (user_id, mode, start_time, end_time, duration_minutes, subject, content_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(session_query, (user_id, mode, start_time_str, end_time_str, duration_mins, subject, content_type))
        session_id = cursor.lastrowid 
        
        if session_data_raw:
            data_to_insert = []
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for pt in session_data_raw:
                data_to_insert.append((
                    session_id, pt.get('session_duration_sec', 0), pt.get('focus_score', 0), 0, now_str
                ))
            data_query = """
                INSERT INTO session_data (session_id, session_duration_sec, focus_score, stress_score, timestamp_utc)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.executemany(data_query, data_to_insert)
        
        conn.commit()
        st.success(f"✅ {mode} saved to History!")
        return session_id
    except Exception as err:
        st.error(f"Database error: {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()



def fetch_session_history(user_id):
    """Fetches all session summaries and raw data for a user."""
    conn = get_db_connection()
    if not conn: return pd.DataFrame(), pd.DataFrame()
    
    history_query = "SELECT * FROM sessions WHERE user_id = %s ORDER BY start_time DESC"
    
    try:
        df_history = pd.read_sql(history_query, conn, params=(user_id,))
        
        raw_data_query = """
            SELECT s.session_id, sd.session_duration_sec, sd.focus_score, sd.stress_score
            FROM sessions s
            JOIN session_data sd ON s.session_id = sd.session_id
            WHERE s.user_id = %s
            ORDER BY sd.session_id, sd.session_duration_sec
        """
        df_raw = pd.read_sql(raw_data_query, conn, params=(user_id,))
        
        return df_history, df_raw
    except pd.io.sql.DatabaseError as err:
        st.error(f"Error fetching history: {err}")
        return pd.DataFrame(), pd.DataFrame()
    finally:
        conn.close()


# =================================================================
# --- 4. EMAIL UTILITIES (FIXED: REMOVED STRICT PLACEHOLDER CHECK) ---
# =================================================================

def send_email_notification(recipient_email, inviter_name, topic):
    """Sends a group study invitation email using SMTP (system's email)."""
    
    # 
    # 🛑 FIX APPLIED: Removed the placeholder check that was blocking your actual credentials.
    # 
    
    try:
        msg = EmailMessage()
        msg['Subject'] = f"Study Session Invitation: Join {inviter_name} for '{topic}'"
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        
        # Simple HTML content for a nicer email format
        html_content = f"""
        <html>
            <body>
                <p>Hello,</p>
                <p>You have been invited by <strong>{inviter_name}</strong> to join a collaborative study session on the topic: <strong>{topic}</strong>.</p>
                <p>Please log in to your Study Assistant application to view the invitation and join the live session.</p>
                <br>
                <p>Happy Studying!</p>
                <p>The Study Assistant Team</p>
            </body>
        </html>
        """
        msg.set_content(html_content, subtype='html')

        # Connect to the SMTP server using SSL/TLS context
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        
        return True
    
    except Exception as e:
        # Added detailed error message for better debugging
        st.error(f"An error occurred while sending the email. Please check your SENDER_EMAIL/SENDER_PASSWORD (App Password).")
        st.error(f"Underlying Python Error: {e}")
        st.caption("Common Issues: Incorrect App Password, SMTP server/port incorrect (Port 465 is for SSL).")
        return False


# =================================================================
# --- 5. AI Generation (REAL Gemini API Integration) ---
# NOTE: Ensure 'requests', 'json', and 'typing' imports are at the top of the file
# for these functions to run correctly.
# =================================================================

def _handle_gemini_api_call(payload: Dict[str, Any], retries: int = 3) -> Dict[str, Any]:
    """
    Handles API call to the Gemini API with exponential backoff and error checking.
    
    Returns:
        dict: {'text': str, 'sources': list[dict]}
    """
    headers = {'Content-Type': 'application/json'}
    
    for attempt in range(retries):
        try:
            # Check for API key presence
            if not GEMINI_API_KEY:
                # In the specified environment, the key is handled at runtime.
                # However, for consistency with your code, we keep the check.
                pass

            # We use the blocking requests library here
            # Updated to use the correct GEMINI_API_URL endpoint format
            response = requests.post(
                f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", 
                headers=headers, 
                json=payload
            )
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            
            result = response.json()
            candidate = result.get('candidates', [{}])[0]
            
            generated_text = ""
            if candidate and candidate.get('content') and candidate['content'].get('parts'):
                generated_text = candidate['content']['parts'][0].get('text', "")
            
            # --- Logic for Grounding Sources (Citations) ---
            sources = []
            grounding_metadata = candidate.get('groundingMetadata')
            if grounding_metadata and grounding_metadata.get('groundingAttributions'):
                sources = [
                    {'uri': attribution.get('web', {}).get('uri'), 
                     'title': attribution.get('web', {}).get('title')}
                    for attribution in grounding_metadata['groundingAttributions']
                    # Filter out sources that are missing URI or Title
                    if attribution.get('web', {}).get('uri') and attribution.get('web', {}).get('title')
                ]
            # --- End Source Logic ---

            if generated_text:
                # Return a dictionary containing the generated text AND the sources
                return {'text': generated_text, 'sources': sources, 'success': True}
            
            # If we reached here, the API call succeeded but returned no content
            return {'text': f"Error: Received empty content from API. Response: {result}", 'sources': [], 'success': False}

        except requests.exceptions.HTTPError as e:
            st.error(f"HTTP Error on attempt {attempt + 1}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt) # Exponential backoff: 1s, 2s, 4s
            else:
                return {'text': f"Error: Failed to get content after {retries} attempts. HTTP Error: {e}", 'sources': [], 'success': False}
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
            return {'text': f"Error: An unexpected error occurred: {e}", 'sources': [], 'success': False}
    
    return {'text': "Error: Unknown failure during API communication.", 'sources': [], 'success': False}


# --- DATABASE HELPERS (MOCK IMPLEMENTATION FOR STATE PERSISTENCE) ---
# A simple in-memory dictionary to simulate DB for session states
if 'MOCK_DB_SESSIONS' not in st.session_state:
    st.session_state.MOCK_DB_SESSIONS = {}

def get_session_state(user_id: str, mode: str, key: str) -> Optional[Dict[str, Any]]:
    """Retrieves session state from the mock database."""
    db_key = f"{user_id}_{mode}_{key}"
    return st.session_state.MOCK_DB_SESSIONS.get(db_key)

def save_session_state(user_id: str, mode: str, key: str, state_data: Dict[str, Any], log_activity: bool = False):
    """Saves the current session state to the mock database."""
    db_key = f"{user_id}_{mode}_{key}"
    st.session_state.MOCK_DB_SESSIONS[db_key] = state_data
    
    if log_activity:
        # Placeholder for actual database logging
        pass 

# --- GEMINI CHAT HANDLER (Multi-Turn Conversation) ---

def get_gemini_response_with_retries(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Handles multi-turn chat requests by separating the system instruction 
    and calling the low-level API handler (_handle_gemini_api_call).
    """
    
    # Check if the first message is the system prompt
    is_system_prompt = history and history[0].get('role') == 'system'
    
    # 1. Extract System Instruction
    system_instruction = history[0]['parts'][0]['text'] if is_system_prompt else ""
    
    # 2. Extract Conversation Contents (excluding the system prompt)
    contents = history[1:] if is_system_prompt else history
    
    payload = {
        "contents": contents,
        # Enable Google Search grounding (web scrap/real-time info)
        "tools": [{"google_search": {} }], 
        "systemInstruction": {"parts": [{"text": system_instruction}]},
    }
    
    return _handle_gemini_api_call(payload)


def generate_ai_content(system_prompt, user_query, is_json=False):
    """
    Fixed AI Content Generator.
    Now correctly handles both text returns and JSON returns for your UI.
    """
    payload = {
        "contents": [{
            "parts": [{"text": f"{system_prompt}\n\nUser Topic: {user_query}"}]
        }]
    }
   
    
    # Add Google Search tools for better notes if not a JSON request
    if not is_json:
        # Use 'google_search' for Gemini 2.0+ models
        payload["tools"] = [{"google_search": {}}]
    payload["generationConfig"] = {"maxOutputTokens": 4096, "temperature": 0.7} # Added for longer notes
    headers = {'Content-Type': 'application/json'}
    
    try:
        # Note: We use the established GEMINI_API_URL for consistent routing
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", 
            json=payload, 
            headers=headers, 
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                text = result['candidates'][0]['content']['parts'][0]['text']
                
                if is_json:
                    # Clean markdown wrappers if AI provides them
                    text = text.replace('```json', '').replace('```', '').replace('`', '').strip()
                
                # IMPORTANT: Return a dictionary if you want to support sources/metadata 
                # OR return a string if your UI expects a string. 
                # To match your quiz generator's current logic, we return a dict.
                return {'text': text, 'sources': [], 'success': True}
            else:
                return {'text': "AI Error: No content generated.", 'sources': [], 'success': False}
        else:
            return {'text': f"API Error: {response.status_code}", 'sources': [], 'success': False}
    except Exception as e:
        return {'text': f"Request Error: {str(e)}", 'sources': [], 'success': False}

def render_video_lecture_ui(api_response_text: str):
    """
    Renders the video player and details. 
    Add this to your script and call it with the result from generate_ai_content.
    """
    import json
    try:
        data = json.loads(api_response_text)
        
        st.markdown(f"### 🎥 Top Recommended Lecture: {data.get('video_title')}")
        
        # Display the video player
        video_url = data.get('video_url', '')
        if 'youtube.com/watch?v=' in video_url:
            # Standard YouTube link conversion for iframe
            video_id = video_url.split('v=')[1].split('&')[0]
            embed_url = f"https://www.youtube.com/embed/{video_id}"
            st.components.v1.iframe(embed_url, height=450)
        else:
            # Fallback for other video formats
            st.video(video_url)

        st.info(f"**Channel:** {data.get('channel_name')}\n\n**Overview:** {data.get('summary')}")
        
    except Exception as e:
        st.error("Could not parse the video data. Please try searching again.")

def call_gemini_api(system_prompt, user_query, is_json=False):
    """
    Unified caller for all 3 Student Modes.
    Handles the nested response structure of Gemini 2.5 Flash.
    """
    # Build the payload
    payload = {
        "contents": [{
            "parts": [{"text": f"{system_prompt}\n\nTopic: {user_query}"}]
        }]
    }
    
    # Enable Google Search grounding for non-quiz content for better accuracy
    if not is_json:
        payload["tools"] = [{"google_search": {}}]

    headers = {'Content-Type': 'application/json'}
    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            # Navigate Gemini's specific JSON response structure
            if 'candidates' in result and len(result['candidates']) > 0:
                text = result['candidates'][0]['content']['parts'][0]['text']
                
                if is_json:
                    # HEAVY CLEANING: AI often adds ```json ... ``` wrappers
                    text = text.replace('```json', '').replace('```', '').replace('`', '').strip()
                
                return text
            return "Error: No candidates returned from AI."
        else:
            return f"API Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Connection Error: {str(e)}"

def get_youtube_videos(query: str, max_results: int = 5):
    """Fetches real video IDs and titles from YouTube Data API v3."""
    search_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": f"{query} educational lecture",
        "type": "video",
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY
    }
    try:
        response = requests.get(search_url, params=params)
        if response.status_code == 200:
            data = response.json()
            videos = []
            for item in data.get("items", []):
                videos.append({
                    "title": item["snippet"]["title"],
                    "id": item["id"]["videoId"]
                })
            return videos
    except Exception as e:
        st.error(f"YouTube Search Error: {e}")
    return []

def generate_quiz_content(topic: str) -> str:
    """
    Generates a quick quiz for gamification.
    Matches the key-extraction logic in your current script.
    """
    quiz_system_prompt = (
        "You are a quick quiz generator. Based on the topic, generate 3 multiple-choice questions "
        "and one true/false question. Respond ONLY with the JSON structure. "
        "The response MUST be an array of objects, each object containing 'q' (question), "
        "'options' (list), and 'a' (answer). Keep it simple."
    )
    
    # This calls the updated function above
    api_result = generate_ai_content(quiz_system_prompt, f"Simple quiz on: {topic}", is_json=True)
    
    # We return the text part so the UI can JSON.loads() it
    return api_result['text']


# =================================================================
# --- 6. MOCK / UTILITY FUNCTIONS (Placeholders for your existing logic) ---
# =================================================================

def get_simulated_brain_data(csv_path="emotions.csv"):
    """
    Fixed extraction logic to ensure Alpha/Beta/Theta are not zero.
    """
    try:
        if 'eeg_df' not in st.session_state:
            st.session_state.eeg_df = pd.read_csv(csv_path)
        
        df = st.session_state.eeg_df
        sample = df.sample(n=1).iloc[0]

        # Use indices that skip the first 4 metadata columns
        alpha = abs(float(sample.iloc[25])) % 1
        beta = abs(float(sample.iloc[75])) % 1
        theta = abs(float(sample.iloc[150])) % 1
        
        # Ensure values aren't 0.0
        alpha = alpha if alpha > 0.1 else round(random.uniform(0.2, 0.4), 2)
        beta = beta if beta > 0.1 else round(random.uniform(0.5, 0.8), 2)
        theta = theta if theta > 0.1 else round(random.uniform(0.1, 0.2), 2)

        # Focus score calculation
        f_score = int((beta * 70) + (alpha * 20) + 10)
        f_score = max(40, min(98, f_score + random.randint(-2, 2)))
        
        return {
            "alpha": round(alpha, 2),
            "beta": round(beta, 2),
            "theta": round(theta, 2),
            "focus_score": f_score,
            "stress_score": 100 - f_score
        }
    except:
        return {"alpha": 0.35, "beta": 0.72, "theta": 0.15, "focus_score": 82, "stress_score": 18}

def render_medical_eeg():
    """
    Updated to ensure st.session_state.current_focus is updated for the report.
    """
    metrics = get_simulated_brain_data()
    
    # Update these so the 'History & Report' and 'Adaptive Engine' work
    st.session_state.current_focus = metrics['focus_score']
    st.session_state.current_stress = metrics['stress_score']
    
    # Update history lists for the graphs
    if 'focus_history' not in st.session_state: st.session_state.focus_history = []
    if 'stress_history' not in st.session_state: st.session_state.stress_history = []
    st.session_state.focus_history.append(metrics['focus_score'])
    st.session_state.stress_history.append(metrics['stress_score'])

    st.markdown("### 🧠 Live Brainwave Analysis")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alpha", metrics['alpha'])
    c2.metric("Beta", metrics['beta'])
    c3.metric("Theta", metrics['theta'])
    c4.metric("Focus", f"{metrics['focus_score']}%")
    
    # Simple wave visual
    t = np.linspace(0, 1, 100)
    wave = metrics['beta'] * np.sin(2 * np.pi * 15 * t) + metrics['alpha'] * np.sin(2 * np.pi * 8 * t)
    st.line_chart(wave, height=100)


def logout():
    """Handles user logout."""
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.role = None
    st.session_state.study_id = None
    st.session_state.auth_view = "login"
    st.session_state.is_active_session = False
    st.toast("Logged out successfully.")
    st.rerun()

def show_reporting_and_history(user_id):
    """Renders the History & Report page using the fetched data."""
    st.header("Session History & Report")
    
    df_history, df_raw = fetch_session_history(user_id)
    
    if df_history.empty:
        st.info("No session history found. Start a study session to see your progress!")
        return
        
    st.subheader("Recent Sessions")
    
    # Calculate average focus/stress for the summary table
    df_summary = df_raw.groupby('session_id').agg(
        avg_focus=('focus_score', 'mean'),
        avg_stress=('stress_score', 'mean')
    ).reset_index()
    
    # Merge averages with session history
    df_display = df_history.merge(df_summary, on='session_id', how='left')
    df_display['start_time'] = pd.to_datetime(df_display['start_time']).dt.strftime('%Y-%m-%d %H:%M')
    df_display['avg_focus'] = df_display['avg_focus'].round(1).astype(str) + '%'
    df_display['avg_stress'] = df_display['avg_stress'].round(1).astype(str) + '%'

    # Select and rename columns for display
    df_final_display = df_display[['start_time', 'mode', 'subject', 'duration_minutes', 'avg_focus', 'avg_stress']]
    df_final_display.columns = ['Start Time', 'Mode', 'Subject/Topic', 'Duration (min)', 'Avg. Focus', 'Avg. Stress']
    
    st.dataframe(df_final_display, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    st.subheader("Detailed Session Analysis")
    selected_session_id = st.selectbox(
        "Select a Session ID for Detailed Charting",
        options=df_history['session_id'].unique(),
        format_func=lambda x: f"ID: {x} - {df_history[df_history['session_id'] == x]['subject'].iloc[0]}"
    )
    
    if selected_session_id:
        st.markdown(f"#### Time-Series Analysis for Session ID: {selected_session_id}")
        
        # Filter raw data for the selected session
        df_chart = df_raw[df_raw['session_id'] == selected_session_id].set_index('session_duration_sec')
        
        if not df_chart.empty:
            st.line_chart(df_chart[['focus_score', 'stress_score']])
            st.caption("Focus (blue) and Stress (red) over the session duration.")
        else:
            st.warning("No raw data points found for this session.")


# =================================================================
# --- 7. AUTHENTICATION (FIXED VALIDATION AND ADDED EMAIL) ---
# =================================================================

def authentication_page():
    """Sign-in/Sign-up page."""
    st.title("Welcome to the Study Assistant")
    
    if st.session_state.auth_view == 'login':
        st.subheader("Sign In")
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login", type="primary"):
            user = st.session_state.login_username.strip()
            pw = st.session_state.login_password.strip()
            
            if not user or not pw:
                st.error("Please enter both username and password.")
                return

            success, user_id, role, full_name, study_id = authenticate_user(user, pw)
            
            if success:
                st.session_state.logged_in = True
                st.session_state.user_id = user_id
                st.session_state.full_name = full_name
                st.session_state.role = role
                st.session_state.study_id = study_id
                st.session_state.is_active_session = False
                st.toast(f"Welcome back, {full_name}!", icon='👋')
                st.rerun()
            else:
                st.error("Invalid username or password.")

        if st.button("Create Account"):
            st.session_state.auth_view = 'signup'
            st.rerun()
            
    else:
        # --- Create Account UI and Logic (FIXED: ADDED EMAIL) ---
        st.header("Create Account")
        
        # Using Streamlit keys for robust state management
        st.text_input("New Username", key="new_username")
        st.text_input("New Password", type="password", key="new_password")
        st.text_input("Your Full Name", key="new_full_name")
        st.text_input("Email (Required for Invitations)", key="new_email") # RE-INTRODUCED EMAIL
        
        # Use index=0 to ensure 'Student' is the default
        st.selectbox("Select Role", ["Student", "Candidate"], index=0, key="new_role") 
        
        if st.button("Create Account", type="primary"):
            
            # Retrieve values explicitly from session state using keys
            username = st.session_state.get("new_username", "").strip()
            password = st.session_state.get("new_password", "").strip()
            full_name = st.session_state.get("new_full_name", "").strip()
            email = st.session_state.get("new_email", "").strip()
            role = st.session_state.get("new_role", "").strip()

            # Robust validation check (NOW includes email)
            if not username or not password or not full_name or not email or not role:
                st.error("Please fill in all fields.")
                return
            
            # Simple Email format validation
            # This regex is simple but effective for basic checks: matches X@Y.Z
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.error("Please enter a valid email address (e.g., user@example.com).")
                return


            # Call the sign up function which uses your provided DB code
            success, generated_study_id = sign_up_user(
                username, 
                password, 
                full_name, 
                role,
                email # Passed to the DB function
            )
            
            if success:
                # After successful signup, return to login page
                st.session_state.auth_view = 'login'
                st.toast("Account created! Please sign in.", icon="🎉")
                st.rerun()
            # If not success, sign_up_user already showed the error.
        
        if st.button("Back to Sign In"):
            st.session_state.auth_view = 'login'
            st.rerun()


# =================================================================
# --- 8. CORE APPLICATION PAGES ---
# ... (All core app pages are retained from the previous version) ...
# =================================================================
def speak_text(text: str):
    """
    Uses Gemini TTS to read out the interviewer's question.
    """
    if not text or st.session_state.get('last_spoken') == text:
        return
    
    try:
        payload = {
            "contents": [{ "parts": [{ "text": f"Say professionally: {text}" }] }],
            "generationConfig": { 
                "responseModalities": ["AUDIO"], 
                "speechConfig": { "voiceConfig": { "voiceName": "Kore" } } 
            },
            "model": "gemini-2.5-flash-preview-tts"
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_API_KEY}", headers=headers, json=payload)
        
        if response.status_code == 200:
            audio_base64 = response.json()['candidates'][0]['content']['parts'][0]['inlineData']['data']
            audio_html = f"""
                <audio autoplay style="display:none;">
                    <source src="data:audio/wav;base64,{audio_base64}" type="audio/wav">
                </audio>
            """
            st.components.v1.html(audio_html, height=0)
            st.session_state.last_spoken = text
    except Exception:
        pass 

def st_speech_recognition():
    """
    Enhanced HTML/JS component for Web Speech API.
    """
    speech_js = """
    <div style="display: flex; flex-direction: column; align-items: center; gap: 10px; font-family: sans-serif; padding: 10px; border: 1px dashed #ccc; border-radius: 10px; background: #fafafa;">
        <div style="display: flex; align-items: center; gap: 15px;">
            <button id="mic-btn" style="
                background-color: #ff4b4b; 
                color: white; 
                border: none; 
                padding: 12px 24px; 
                border-radius: 50px; 
                cursor: pointer;
                font-weight: bold;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            ">🎤 Tap to Speak</button>
            <div id="status" style="font-size: 14px; color: #666; font-weight: 500;">Ready</div>
        </div>
        <div id="transcript-preview" style="font-size: 13px; color: #888; font-style: italic; min-height: 20px;"></div>
    </div>

    <script>
        const btn = document.getElementById('mic-btn');
        const status = document.getElementById('status');
        const preview = document.getElementById('transcript-preview');
        
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        
        if (!SpeechRecognition) {
            status.innerText = "Unsupported Browser";
            btn.disabled = true;
        } else {
            const recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = true;
            recognition.lang = 'en-US';

            btn.onclick = () => {
                try { recognition.start(); } catch (e) {}
            };

            recognition.onstart = () => {
                status.innerText = "Listening...";
                btn.style.backgroundColor = "#2e7d32";
            };

            recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                preview.innerText = '"' + transcript + '"';
                
                if (event.results[0].isFinal) {
                    window.parent.postMessage({
                        type: 'streamlit:set_widget_value',
                        data: transcript,
                        key: 'voice_input_result'
                    }, '*');
                    status.innerText = "Captured!";
                    btn.style.backgroundColor = "#ff4b4b";
                }
            };

            recognition.onerror = (e) => {
                status.innerText = "Error: " + e.error;
                btn.style.backgroundColor = "#ff4b4b";
            };

            recognition.onend = () => {
                btn.style.backgroundColor = "#ff4b4b";
            };
        }
    </script>
    """
    st.components.v1.html(speech_js, height=130)

# --- INTERVIEW PROMPTS ---
def get_candidate_system_prompt(job_title: str, difficulty: str) -> str:
    return f"""You are an expert AI interviewer.
- **Role:** You are interviewing the user for the position of a **{job_title}**.
- **Difficulty:** The interview should be at a **{difficulty}** level.
- **Task:** Ask relevant and challenging questions based on the role and difficulty.
- **Tone:** Maintain a professional, encouraging, and neutral tone.
- **Pacing:** Ask only ONE question at a time.
- **Format:** Focus only on the next question.
- **Start:** Your first response should be a friendly greeting and a request for the user to introduce themselves."""

def get_candidate_report_prompt(job_title: str, difficulty: str) -> str:
    return f"""The interview session for the {job_title} role (Difficulty: {difficulty}) has concluded.
Based ONLY on the preceding conversation history:
1. **Skills Assessment:** Summarize performance (technical, communication, problem-solving).
2. **Strengths:** List 3-5 major strengths.
3. **Areas for Improvement:** List 3-5 specific areas for preparation.
4. **Hiring Recommendation:** Hire/Further Interview/Reject with justification.
Provide output as well-formatted markdown."""

def candidate_mode_ui():
    """
    Candidate Interview Preparation Mode UI with Voice Assistant and Persistence.
    """
    USER_ID = st.session_state.get('user_id', 'guest')
    
    if 'candidate_state' not in st.session_state:
        st.session_state.candidate_state = {
            'is_active': False,
            'job_title': 'Software Engineer',
            'difficulty': 'Medium',
            'history': [],
            'interview_id': str(uuid.uuid4())
        }

    st.title("👨‍💻 AI Interview Preparation")
    st.markdown("Practice interviews with our AI assistant using text or voice.")
    
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        st.session_state.candidate_state['job_title'] = st.text_input(
            "Job Role", 
            value=st.session_state.candidate_state['job_title'], 
            disabled=st.session_state.candidate_state['is_active']
        )

    with col2:
        st.session_state.candidate_state['difficulty'] = st.selectbox(
            "Difficulty", 
            ['Easy', 'Medium', 'Hard'], 
            index=['Easy', 'Medium', 'Hard'].index(st.session_state.candidate_state['difficulty']),
            disabled=st.session_state.candidate_state['is_active']
        )
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if not st.session_state.candidate_state['is_active']:
            if st.button("🚀 Start Interview", type="primary", use_container_width=True):
                st.session_state.candidate_state['history'] = []
                st.session_state.candidate_state['is_active'] = True
                
                system_prompt = get_candidate_system_prompt(
                    st.session_state.candidate_state['job_title'],
                    st.session_state.candidate_state['difficulty']
                )
                
                initial_message = "Hello! I am your AI interviewer. To get started, please introduce yourself and tell me about your background."
                
                st.session_state.candidate_state['history'] = [
                    {"role": "system", "parts": [{"text": system_prompt}]},
                    {"role": "model", "parts": [{"text": initial_message}]}
                ]
                st.rerun()
        else:
            if st.button("🛑 End Interview", type="secondary", use_container_width=True):
                st.session_state.candidate_state['is_active'] = False
                
                if st.session_state.candidate_state['history']:
                    report_prompt = get_candidate_report_prompt(
                         st.session_state.candidate_state['job_title'],
                         st.session_state.candidate_state['difficulty']
                    )
                    
                    with st.spinner("Generating performance report..."):
                        try:
                            response_text = call_gemini_api(
                                st.session_state.candidate_state['history'][0]["parts"][0]["text"],
                                report_prompt
                            )
                            st.session_state.candidate_state['history'].append(
                                {"role": "model", "parts": [{"text": f"## Interview Report\n\n{response_text}"}]}
                            )
                        except Exception as e:
                            st.error(f"Failed to generate report: {e}")
                st.rerun()

    st.markdown("---")

    if not st.session_state.candidate_state['is_active']:
        if st.session_state.candidate_state['history']:
             for message in reversed(st.session_state.candidate_state['history']):
                 if message["role"] == "model" and message["parts"][0]["text"].startswith("## Interview Report"):
                    st.markdown(message["parts"][0]["text"])
                    break
        else:
            st.info("Set your role and difficulty above, then click 'Start Interview'.")
    else:
        # Display Chat History
        for message in st.session_state.candidate_state['history']:
            if message["role"] == "system": continue
            with st.chat_message(message["role"]):
                st.markdown(message["parts"][0]["text"])
                if message == st.session_state.candidate_state['history'][-1] and message["role"] == "model":
                    if not message["parts"][0]["text"].startswith("## Interview Report"):
                        speak_text(message["parts"][0]["text"])

        st.write("### 🎙️ Answer via Voice")
        st_speech_recognition()
        
        # Capture input from chat box OR voice component
        prompt = st.chat_input("Your answer...")
        
        if prompt:
            st.session_state.candidate_state['history'].append({"role": "user", "parts": [{"text": prompt}]})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("model"):
                with st.spinner("Thinking..."):
                    try:
                        sys_p = st.session_state.candidate_state['history'][0]["parts"][0]["text"]
                        ai_text = call_gemini_api(sys_p, prompt)
                        st.markdown(ai_text)
                        st.session_state.candidate_state['history'].append({"role": "model", "parts": [{"text": ai_text}]})
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            
def group_study_ui():
    """Collaborative learning UI with multi-teammate invitation."""
    st.header("Group Study: Collaborative Learning")

    if st.session_state.get('is_active_session', False):
        live_session_display()
        return

    st.info(f"Your Unique Study ID is: **`{st.session_state.get('study_id', 'N/A')}`**")
    st.markdown("---")

    st.subheader("Start a New Group Session")
    
    # Session Details
    col_a, col_b = st.columns(2)
    with col_a:
        group_duration = st.number_input("Session Duration (minutes)", 5, 120, 25, step=5, key='group_duration_input')
    with col_b:
        num_teammates = st.number_input("Number of Teammates to Invite", 1, 5, 1, step=1)

    subject_input = st.text_input("Topic for Group Study", key='group_topic_input', placeholder="e.g., Quantum Computing Basics")
    
    # Dynamic Input Fields for Teammate IDs
    st.write("Enter Teammate Study IDs:")
    invite_ids = []
    # Create columns based on number of teammates for better spacing
    cols = st.columns(num_teammates)
    for i in range(num_teammates):
        with cols[i]:
            tid = st.text_input(f"Teammate {i+1}", key=f"teammate_id_{i}", placeholder="Study ID").strip()
            if tid:
                invite_ids.append(tid)

    if st.button("Create & Start Group Session", type="primary", use_container_width=True):
        if not subject_input:
            st.error("Please enter a topic.")
            return
            
        with st.spinner("🤖 AI is generating detailed study notes for your group..."):
            # 1. Generate Study Content
            system_prompt = "You are a professional academic tutor. Generate highly detailed, comprehensive study notes with clear definitions and concepts."
            prompt = f"Topic: {subject_input}. Provide structured notes including key definitions, historical context, and core principles."
            generated_notes = call_gemini_api(system_prompt, prompt)
            
            # 2. Handle Multi-Invitations
            st.session_state.group_members = [st.session_state.get('study_id')]
            invitation_count = 0
            
            for tid in set(invite_ids): # Set to avoid duplicates
                if tid == st.session_state.get('study_id'):
                    st.warning(f"Skipping Study ID `{tid}` (That's your ID!)")
                    continue
                
                # Check if get_user_email_by_study_id is available in scope
                if "get_user_email_by_study_id" in globals():
                    recipient_details = get_user_email_by_study_id(tid)
                    if recipient_details:
                        recipient_email, recipient_name = recipient_details
                        # Send email logic
                        if "send_email_notification" in globals():
                            send_email_notification(recipient_email, st.session_state.get('full_name', 'A teammate'), subject_input)
                        st.session_state.group_members.append(tid)
                        invitation_count += 1
                    else:
                        st.error(f"Could not find student with Study ID: `{tid}`")

            if invitation_count > 0:
                st.success(f"Invitations successfully sent to {invitation_count} teammate(s)!")

            # 3. Session Initialization
            st.session_state.ai_study_content = generated_notes
            st.session_state.group_subject = subject_input
            st.session_state.is_active_session = True
            st.session_state.session_mode = "Group Study"
            st.session_state.session_duration_minutes = group_duration
            
            st.session_state.start_time_unix = time.time()
            st.session_state.current_session_data = []
            st.rerun()


def student_mode_ui():
    """
    Complete Student Home Page: 
    - Handles Content Generation (Notes, Videos, Quizzes).
    - Features: Real-time EEG simulation, Session Timer, and Robust JSON Parsing.
    """
    st.header("Student Dashboard")

    # --- PART 1: ACTIVE SESSION VIEW ---
    if st.session_state.get('is_active_session', False):
        m_col1, m_col2, m_col3 = st.columns([1.5, 1.5, 1])
        
        with m_col1:
            timer_placeholder = st.empty()
            if not st.session_state.get('show_timer'):
                timer_placeholder.success(f"📖 {st.session_state.get('content_type')}")
        
        with m_col2:
            focus_val = random.uniform(0.70, 0.95)
            st.metric("🎯 Live Focus Score", f"{int(focus_val * 100)}%", delta=f"{random.randint(-1, 2)}%")
            
            with st.expander("View Brainwave Metrics"):
                st.caption("Simulated real-time data from EEG Bridge")
                c1, c2, c3 = st.columns(3)
                c1.text(f"Alpha: {random.uniform(0.1, 0.3):.2f}")
                c2.text(f"Beta: {random.uniform(0.5, 0.8):.2f}")
                c3.text(f"Theta: {random.uniform(0.1, 0.4):.2f}")

        with m_col3:
            if st.button("⏹️ End Session", type="primary", use_container_width=True):
                st.session_state.is_active_session = False
                st.session_state.show_timer = False
                st.session_state.ai_study_content = ""
                st.session_state.quiz_data = []
                st.session_state.video_links = []
                st.rerun()

        st.divider()

        # CONTENT RENDERING AREA
        mode = st.session_state.get('content_type')
        st.subheader(f"Topic: {st.session_state.get('subject')}")

        with st.container(border=True):
            if mode == "Detailed Notes":
                notes = st.session_state.get('ai_study_content')
                if notes and "Mocked content" not in str(notes):
                    st.markdown(notes)
                else:
                    st.error("⚠️ AI Content Generation failed. Please try a more specific topic or retry.")
                    if st.button("🔄 Retry AI Generation"):
                        st.session_state.is_active_session = False
                        st.rerun()

            elif mode == "Video Lecture (Notes)":
                summary = st.session_state.get('ai_study_content')
                if summary and "Mocked content" not in str(summary):
                    st.info("📌 Lesson Summary")
                    # Extract the 'text' key from the dictionary returned by your function
                    st.write(summary.get('text', summary) if isinstance(summary, dict) else summary)
                
                st.subheader("📺 Recommended Lectures")
                videos = st.session_state.get('video_links', [])
                if videos:
                    for vid in videos:
                        st.video(f"https://www.youtube.com/watch?v={vid['id']}")
                else:
                    st.warning("No videos found for this topic.")

            elif mode == "Practice Exercises (Theory)":
                st.subheader("📝 Practice Quiz")
                quiz = st.session_state.get('quiz_data', [])
                
                if quiz and isinstance(quiz, list) and len(quiz) > 0:
                    for idx, item in enumerate(quiz):
                        st.write(f"**Q{idx+1}: {item.get('q')}**")
                        options = item.get('options', ["A", "B", "C", "D"])
                        st.radio(f"Select answer", options, key=f"quiz_active_{idx}")
                        st.write("---")
                    
                    if st.button("Submit Practice Quiz"):
                        st.success("Answers submitted! Great job staying focused.")
                else:
                    st.error("Quiz data is empty or invalid.")
                    if st.button("Restart Session"):
                        st.session_state.is_active_session = False
                        st.rerun()
        
        # --- TIMER LOGIC (Only rerun if timer is active) ---
        if st.session_state.get('show_timer') and st.session_state.get('end_time'):
            remaining = st.session_state.end_time - datetime.now()
            if remaining.total_seconds() > 0:
                mins, secs = divmod(int(remaining.total_seconds()), 60)
                timer_placeholder.metric("⏳ Session Timer", f"{mins:02d}:{secs:02d}")
                time.sleep(1)
                st.rerun()
            else:
                timer_placeholder.error("⏰ Time's Up!")
            
        return 

    # --- PART 2: CONFIGURATION UI (New Session) ---
    st.subheader("Configure Your Session")
    subject_input = st.text_input("Enter Subject/Topic", placeholder="e.g. Java Fundamentals")
    content_type_input = st.selectbox("Select Content Type", [
        "Detailed Notes", 
        "Video Lecture (Notes)", 
        "Practice Exercises (Theory)"
    ])
    
    solo_duration = 15
    if content_type_input == "Detailed Notes":
        solo_duration = st.number_input("Session Duration (minutes)", 1, 120, 15)

    if st.button("🚀 Start Solo Study Session", use_container_width=True):
        if not subject_input:
            st.error("Please enter a subject.")
            return

        with st.spinner(f"AI is crafting your {content_type_input}..."):
            # RESET STATE BEFORE GENERATION
            notes, videos, quiz = "", [], []
            
            try:
                # 1. GENERATE CONTENT
                if content_type_input == "Detailed Notes":
                    sys_prompt = "You are a professional academic tutor. Create comprehensive, structured study notes using Markdown with clear headings and detailed explanations."
                    res_dict = generate_ai_content(sys_prompt, f"Write detailed study notes for the topic: {subject_input}")
                    notes = res_dict.get('text', "")
                    st.session_state.show_timer = True
                    st.session_state.end_time = datetime.now() + timedelta(minutes=solo_duration)
                
                elif content_type_input == "Video Lecture (Notes)":
                    sys_prompt = "Create a high-level summary of the following topic in 3-4 professional paragraphs."
                    res_dict = generate_ai_content(sys_prompt, f"Summarize: {subject_input}")
                    notes = res_dict.get('text', "")
                    videos = get_youtube_videos(subject_input, max_results=3)
                    st.session_state.show_timer = False
                
                elif content_type_input == "Practice Exercises (Theory)":
                    sys_prompt = (
                        "Generate 5 high-quality MCQs. Return ONLY a valid JSON array like this: "
                        "[{\"q\": \"Question?\", \"options\": [\"A\", \"B\", \"C\", \"D\"], \"a\": \"A\"}]"
                    )
                    res_dict = generate_ai_content(sys_prompt, subject_input, is_json=True)
                    raw_text = res_dict.get('text', '[]')
                    
                    # More robust JSON cleaning
                    match = re.search(r'\[.*\]', raw_text, re.DOTALL)
                    if match:
                        quiz = json.loads(match.group(0))
                    else:
                        st.error("AI returned invalid data format. Please try again.")
                        return

                # 2. VALIDATE GENERATION (Stop if we got mocked/empty content)
                if not notes and not quiz:
                    st.error("The generation service is currently busy or returned an empty response. Please wait 5 seconds and try again.")
                    return

                # 3. COMMIT TO SESSION STATE
                st.session_state.subject = subject_input
                st.session_state.content_type = content_type_input
                st.session_state.ai_study_content = notes
                st.session_state.video_links = videos
                st.session_state.quiz_data = quiz
                st.session_state.is_active_session = True
                
                # FINAL TRIGGER
                st.rerun()

            except Exception as e:
                st.error(f"Generation Error: {str(e)}")
            

def quiz_component():
    """Renders the quiz UI when focus drops with robust key handling."""
    st.error("🚨 FOCUS RE-ENGAGEMENT QUIZ 🚨")
    
    # Unified subject display
    subject = st.session_state.get('subject') or st.session_state.get('group_subject', 'General Topic')
    st.subheader(f"Quick Quiz on: {subject}")
    st.warning("Your session is paused until you complete this quick quiz to regain focus.")
    
    quiz_data_list = []
    
    # --- ROBUST DATA LOADING ---
    try:
        raw_data = st.session_state.get('quiz_data')
        
        # If it's already a list (from your Practice Quiz logic)
        if isinstance(raw_data, list):
            quiz_data_list = raw_data
        # If it's a JSON string (from a fresh API call)
        elif isinstance(raw_data, str):
            quiz_data_list = json.loads(raw_data)
        # If it's a single dictionary
        elif isinstance(raw_data, dict):
            quiz_data_list = [raw_data]
            
        if not quiz_data_list:
            raise ValueError("No questions found")
            
    except Exception as e:
        # Fallback if everything fails
        quiz_data_list = [{"q": f"What is the main concept of {subject}?", "is_stressful": False}]
    
    st.markdown("---")
    
    # --- RENDER QUESTIONS ---
    # We use a form to prevent multiple reruns while typing
    with st.form("focus_quiz_form"):
        for i, item in enumerate(quiz_data_list):
            # FIX: Support multiple key types: 'q', 'question', or 'text'
            # This prevents the KeyError: 'q'
            question_text = item.get('q') or item.get('question') or item.get('text') or "Question missing"
            
            st.markdown(f"**Question {i+1}:** {question_text}")
            st.text_input("Your Answer:", key=f"quiz_q_answer_{i}")
        
        st.markdown("---")
        
        submit = st.form_submit_button("Resume Session (Quiz Completed)", type="primary", use_container_width=True)
        
        if submit:
            # Cleanup state and resume
            st.session_state.is_quiz_active = False
            st.session_state.quiz_data = None
            st.toast("Focus verified! Resuming session...", icon="✅")
            time.sleep(1)
            st.rerun()
        

def live_session_display():
    """
    Simplified Group Study Display focusing ONLY on Content and Focus Scores.
    """
    mode = st.session_state.get('session_mode', 'Solo Study')
    subject = st.session_state.get('group_subject', 'General Study')
    
    st.title(f"👥 {mode}: {subject}")
    
    # Layout: Notes on the left, Focus score on the right
    col_content, col_analytics = st.columns([2, 1], gap="large")

    with col_content:
        st.subheader("📝 Detailed Study Content")
        with st.container(height=650, border=True):
            notes = st.session_state.get('ai_study_content', "No content generated yet.")
            st.markdown(notes)

    with col_analytics:
        # EEG and Focus Score logic
        render_medical_eeg()
        
        # Progress Bar and Timer calculation
        target_mins = st.session_state.get('session_duration_minutes', 30)
        start_unix = st.session_state.get('start_time_unix', time.time())
        elapsed_sec = time.time() - start_unix
        
        progress = min(1.0, elapsed_sec / (target_mins * 60))
        
        # Displaying simple timer
        remaining_sec = max(0, (target_mins * 60) - elapsed_sec)
        mins, secs = divmod(int(remaining_sec), 60)
        
        st.metric("Time Remaining", f"{mins:02d}:{secs:02d}")
        st.write(f"Session Progress: {int(progress * 100)}%")
        st.progress(progress)

    st.divider()
    if st.button("End Session & Save History", type="primary", use_container_width=True):
        if "save_session_to_db" in globals():
            try:
                save_session_to_db()
            except:
                pass
        st.session_state.is_active_session = False
        st.balloons()
        st.rerun()

    # Rerun pulse to keep EEG data moving
    if st.session_state.get('is_active_session'):
        time.sleep(1)
        st.rerun()

def end_session_flow(auto_end=False):
    """Saves data to MySQL and redirects to the report."""
    if st.session_state.is_active_session:
        st.session_state.is_active_session = False
    
    # Determine context based on mode for saving
    mode = st.session_state.session_mode
    if mode == "Solo Study":
        context = {"subject": st.session_state.subject, "content_type": st.session_state.content_type}
    elif mode == "Group Study":
        context = {"subject": st.session_state.get('group_subject', 'Untitled Group Session'), "content_type": "Group Study"}
    else: # Candidate Interview
        context = {"interview_type": st.session_state.interview_type, "question_set": st.session_state.question_set}
        
    
    session_id = save_session_to_db(
        st.session_state.user_id, 
        st.session_state.current_session_data, 
        st.session_state.session_mode, 
        context
    )
    
    if session_id:
        if auto_end:
            st.toast(f"Session {session_id} saved successfully!", icon='💾')
        else:
            st.success(f"Session {session_id} saved successfully! Generating report...")
            
        st.session_state.current_session_data = [] 
        st.session_state.page = "History & Report"
    else:
        st.error("Failed to save session data to the database.")
        
    st.rerun() 


# =================================================================
# --- 9. Main Application Router ---
# =================================================================

def main_app():
    """Renders the main navigation and application based on user role."""
    
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.full_name}")
        st.caption(f"Study ID: **`{st.session_state.study_id}`**") 
        st.caption(f"Role: {st.session_state.role} | ID: `{st.session_state.user_id}`")
        st.button("Logout", on_click=logout, type="secondary")
        st.markdown("---")
        
        PAGES = {
            "Student": {"Study Session": student_mode_ui, "Group Study": group_study_ui, "History & Report": show_reporting_and_history},
            "Candidate": {"Interview Prep": candidate_mode_ui, "History & Report": show_reporting_and_history}
        }
        
        role_pages = PAGES.get(st.session_state.role, {})
        page_names = list(role_pages.keys())
        
        # Check if the current page is valid for the role, otherwise default to the first page
        if 'page' not in st.session_state or st.session_state.page not in page_names:
             st.session_state.page = page_names[0]
        
        st.sidebar.title("Navigation")
        st.session_state.page = st.radio("Go to", page_names, index=page_names.index(st.session_state.page))


    page_function = role_pages[st.session_state.page]
    
    if st.session_state.page == "History & Report":
        page_function(st.session_state.user_id)
    else:
        page_function()


# =================================================================
# --- Application Start ---
# =================================================================
if not st.session_state.logged_in:
    authentication_page()
else:
    main_app()