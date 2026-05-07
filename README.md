AI-Powered Adaptive Learning & Career Readiness Platform.

An intelligent educational ecosystem that combines Generative AI with Neuro-simulation to personalize study sessions and streamline interview preparation. This platform leverages real-time focus monitoring (simulated) to adapt content delivery based on the user's mental state.

🚀 Key Features

📖 Student Mode

Adaptive Study Material: Generates detailed Markdown notes on any subject using Gemini 2.5 Flash.

Automated Video Sourcing: Dynamically fetches relevant educational lectures via the YouTube Data API.

Simulated Focus Monitoring: Uses stochastic mathematical models to simulate EEG (Alpha, Beta, Theta) waves.

Smart Alerts: Triggers "Focus Nudges" if simulated brainwave patterns indicate a lack of attention.

💼 Candidate Mode

Role-Specific Interviews: AI-driven technical and behavioral interview roleplay for various job titles.

Real-time Evaluation: Instant feedback and scoring on interview performance stored directly in the database.

👥 Collaborative Group Study

Live Leaderboards: Real-time synchronization of focus scores among group members using Firebase Firestore.

Shared Session IDs: Collaborative rooms for peer-to-peer study tracking.

🛠️ Technical Stack

Frontend: Streamlit (Interactive Web Dashboard)

AI Engine: Google Gemini 2.5 Flash (Content Generation & Interview Logic)

Database: Firebase Firestore (Session persistence, User History, and Group Sync)

Video Integration: YouTube Data API v3

Data Simulation: NumPy & Pandas (Mathematical EEG wave generation)

Communication: SMTP (Automated Session Reports & OTPs)

🧬 How the Simulation Works (Hardware-Free)

This project is designed to be fully accessible without external EEG hardware.

Simulated Patterns: Instead of physical sensors, the application retrieves "mental state" patterns from a dedicated collection in Firebase.

Beta-to-Theta Ratio: The system calculates a focus percentage by analyzing the ratio between simulated Beta (active) and Theta (drowsy) waves.

Consistency: By using a database-centric approach, session history and focus trends remain consistent and persistent for every user.

📥 Installation & Setup

Clone the repository:

Bash
git clone https://github.com/your-username/your-repo-name.git

cd your-repo-name
Install dependencies:

Bash
pip install -r requirements.txt

Configure API Keys:
Create a .env file or update the configuration section in app.py with your credentials:
GEMINI_API_KEY
YOUTUBE_API_KEY

Firebase Service Account Credentials

SMTP Email & App Password

Run the application:

Bash
streamlit run app.py

📊 Project Impact
This platform demonstrates a scalable architecture for EdTech, showing how Generative AI can be used not just for content creation, but as a proactive assistant that monitors and responds to simulated behavioral data to improve learning outcomes.
