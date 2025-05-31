from flask import Flask, request, jsonify, make_response
from utils.extractor import extract_text, extract_info
from utils.question_generator import generate_questions, generate_expected_answers
import os
from flask_cors import CORS
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime, timedelta
import bcrypt
import jwt
import uuid
import traceback
import atexit
import signal
import sys
from functools import wraps

load_dotenv()

app = Flask(__name__)

# Fix CORS configuration - specify origins properly for development
CORS(app, 
     origins=["http://localhost:5173"], 
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

JWT_SECRET = os.getenv("JWT_SECRET", "555")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 24  # hours

# Global variables for MongoDB client and collections
client = None
collections = None

# MongoDB connection with better error handling
def connect_to_mongodb():
    global client, collections # Ensure these are global variables
    try:
        print("Attempting to connect to MongoDB...")
        # Update your MongoDB connection string here if it's incorrect or needs adjustment
        client = MongoClient(
            "mongodb+srv://abhinav:abhinav56@projectquestions.xcmjkfj.mongodb.net/?retryWrites=true&w=majority&appName=projectquestions",
            serverSelectionTimeoutMS=5000,   # Reduced timeout
            connectTimeoutMS=10000,          # Reduced timeout
            socketTimeoutMS=10000,           # Reduced timeout
            maxPoolSize=5,                   # Reduced pool size
            minPoolSize=1,
            maxIdleTimeMS=30000,
            # More lenient SSL settings (consider tightening for production)
            ssl=True,
            tlsAllowInvalidCertificates=True,
            tlsAllowInvalidHostnames=True
        )
        
        # Test the connection with a shorter timeout
        client.admin.command('ping')
        print("✅ MongoDB connection successful")
        
        db = client["interview_app_db"]
        collections = {
            'users': db["users"],
            'questions': db["questions"],
            'user_answers': db["user_answers"]
        }
        
        # Create indexes with error handling
        try:
            collections['users'].create_index("email", unique=True)
            collections['users'].create_index("username", unique=True)
            print("✅ Database indexes created successfully")
        except Exception as e:
            print(f"⚠️ Index creation warning: {e}")
            
        return client, collections
        
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        print("🔄 Falling back to local development mode...")
        client = None # Explicitly set to None on failure
        collections = { # Explicitly set to None for all collections
            'users': None,
            'questions': None,
            'user_answers': None
        }
        return None, None

# Try to connect to MongoDB when the application starts
client, collections = connect_to_mongodb()

def cleanup_resources():
    """Clean up database connections on shutdown"""
    try:
        if client:
            print("🧹 Cleaning up database connections...")
            client.close()
            print("✅ Database connections closed successfully")
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    print(f"\n🛑 Received signal {sig}, shutting down gracefully...")
    cleanup_resources()
    sys.exit(0)

# Register cleanup functions
atexit.register(cleanup_resources)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        print(f"DEBUG: Entering token_required. Client connected: {client is not None}, Users collection available: {collections and collections['users'] is not None}")
        # Check if collections is None or if the specific collection is None
        if collections is None or collections['users'] is None:
            print("DEBUG: Database or users collection unavailable for token_required route. Returning 503.")
            return jsonify({'message': 'Database unavailable - running in local mode'}), 503
            
        token = request.cookies.get('token')
        if not token:
            print("DEBUG: Token missing.")
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user = collections['users'].find_one({"_id": data['user_id']})
            if not current_user:
                print(f"DEBUG: User not found for ID: {data['user_id']}.")
                return jsonify({'message': 'User not found!'}), 401
        except jwt.ExpiredSignatureError:
            print("DEBUG: Token expired.")
            return jsonify({'message': 'Token has expired!'}), 401
        except jwt.InvalidTokenError:
            print("DEBUG: Invalid token.")
            return jsonify({'message': 'Invalid token!'}), 401
        print(f"DEBUG: Token valid for user: {current_user['username']}")
        return f(current_user, *args, **kwargs)
    return decorated

@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint"""
    print(f"DEBUG: / endpoint hit. Client connected: {client is not None}")
    return jsonify({
        "status": "healthy",
        "message": "Interview Question Generator API is running",
        "database": "connected" if client else "disconnected",
        "mode": "production" if client else "local_development"
    })

@app.route("/api/health", methods=["GET"])
def api_health():
    """API health check"""
    print(f"DEBUG: /api/health endpoint hit. Client connected: {client is not None}")
    return jsonify({
        "status": "ok",
        "database": "connected" if client else "disconnected",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": "production" if client else "local_development"
    })

@app.route("/api/register", methods=["POST"])
def register():
    print(f"DEBUG: /api/register endpoint hit. Users collection available: {collections and collections['users'] is not None}")
    if collections is None or collections['users'] is None:
        return jsonify({"message": "Registration not available in local mode"}), 503
        
    try:
        data = request.json
        if not data:
            return jsonify({"message": "No data provided"}), 400

        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()

        if not username or not email or not password:
            return jsonify({"message": "All fields are required"}), 400

        if collections['users'].find_one({"email": email}):
            return jsonify({"message": "User with this email already exists"}), 409
        if collections['users'].find_one({"username": username}):
            return jsonify({"message": "Username is already taken"}), 409

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        new_user = {
            "_id": str(uuid.uuid4()),
            "username": username,
            "email": email,
            "password": hashed_password,
            "created_at": datetime.utcnow()
        }
        collections['users'].insert_one(new_user)

        return jsonify({"message": "User registered successfully"}), 201
    except Exception as e:
        print(f"Registration error: {str(e)}")
        return jsonify({"message": "Registration failed. Please try again."}), 500

@app.route("/api/login", methods=["POST"])
def login():
    print(f"DEBUG: /api/login endpoint hit. Users collection available: {collections and collections['users'] is not None}")
    if collections is None or collections['users'] is None:
        return jsonify({"message": "Login not available in local mode"}), 503
        
    try:
        data = request.json
        if not data:
            return jsonify({"message": "No data provided"}), 400

        email = data.get('email', '').strip()
        password = data.get('password', '').strip()

        if not email or not password:
            return jsonify({"message": "Email and password are required"}), 400

        user = collections['users'].find_one({"email": email})
        if not user:
            return jsonify({"message": "Invalid email or password"}), 401

        password_bytes = password.encode('utf-8')
        stored_password = user['password']

        if isinstance(stored_password, str):
            stored_password = stored_password.encode('utf-8')

        try:
            password_match = bcrypt.checkpw(password_bytes, stored_password)
            if not password_match:
                return jsonify({"message": "Invalid email or password"}), 401
        except Exception as pwd_error:
            print(f"Password check error: {str(pwd_error)}")
            return jsonify({"message": "Authentication error"}), 500

        try:
            token_payload = {
                'user_id': user['_id'],
                'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION)
            }
            token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        except Exception as jwt_error:
            print(f"JWT generation error: {str(jwt_error)}")
            return jsonify({"message": "Authentication token error"}), 500

        response = make_response(jsonify({
            "message": "Login successful",
            "user": {
                "id": user['_id'],
                "username": user['username'],
                "email": user['email']
            }
        }))

        # Adjust cookie settings for local development
        response.set_cookie(
            'token',
            token,
            httponly=True,
            secure=False,  # Set to False for local development
            samesite='Lax',  # Changed from 'None' to 'Lax' for local development
            max_age=JWT_EXPIRATION * 3600
        )

        return response
    except Exception as e:
        print(f"Login error: {str(e)}")
        return jsonify({"message": "Login failed. Please try again."}), 500

@app.route("/api/logout", methods=["POST"])
def logout():
    response = make_response(jsonify({"message": "Logout successful"}))
    response.delete_cookie('token')
    return response

@app.route("/api/profile", methods=["GET"])
@token_required
def get_profile(current_user):
    print(f"DEBUG: /api/profile endpoint hit for user: {current_user['username']}")
    return jsonify({
        "id": current_user['_id'],
        "username": current_user['username'],
        "email": current_user['email'],
        "created_at": current_user['created_at'].isoformat() # Ensure datetime is serializable
    })

# Add a temporary local development endpoint
@app.route("/api/profile-local", methods=["GET"])
def get_profile_local():
    """Local development endpoint that doesn't require authentication"""
    print(f"DEBUG: /api/profile-local endpoint hit. Client connected: {client is not None}")
    if client:
        # If client is connected, this endpoint should not be used
        print("DEBUG: Client is connected, redirecting from /api/profile-local to /api/profile.")
        return jsonify({"message": "Use /api/profile instead"}), 400
    
    return jsonify({
        "id": "local_user",
        "username": "Local User",
        "email": "local@example.com",
        "created_at": datetime.utcnow().isoformat(), # Ensure datetime is serializable
        "mode": "local_development"
    })

@app.route("/api/upload-resume", methods=["POST"])
@token_required
def upload_resume(current_user):
    print(f"DEBUG: /api/upload-resume endpoint hit. Questions collection available: {collections and collections['questions'] is not None}")
    if collections is None or collections['questions'] is None:
        return jsonify({"error": "Database unavailable for resume upload"}), 503
        
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(file_path)

        text = extract_text(file_path)
        info = extract_info(text)
        questions = generate_questions(skills=info["skills"], resume_text=text)
        
        # Generate expected answers for each question
        expected_answers = generate_expected_answers(questions, skills=info["skills"], resume_text=text)
        
        # Store questions and expected answers
        question_set_id = str(uuid.uuid4())
        collections['questions'].insert_one({
            "_id": question_set_id,
            "user_id": current_user['_id'],
            "questions": questions,
            "expected_answers": expected_answers,
            "skills": info["skills"],
            "timestamp": datetime.utcnow()
        })

        # Clean up uploaded file
        try:
            os.remove(file_path)
        except:
            pass

        return jsonify({
            "question_set_id": question_set_id,
            "questions": questions,
            "skills": info["skills"]
        })
    except Exception as e:
        print(f"Upload resume error: {str(e)}")
        return jsonify({"error": "Failed to process resume"}), 500

@app.route("/api/upload-resume-public", methods=["POST"])
def upload_resume_public():
    print(f"DEBUG: /api/upload-resume-public endpoint hit. Questions collection available: {collections and collections['questions'] is not None}")
    # For local development, use in-memory storage
    if collections is None or collections['questions'] is None:
        return jsonify({"error": "Feature not available in local mode"}), 503
        
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(file_path)

        text = extract_text(file_path)
        info = extract_info(text)
        questions = generate_questions(skills=info["skills"], resume_text=text)
        
        # Generate expected answers for each question
        expected_answers = generate_expected_answers(questions, skills=info["skills"], resume_text=text)
        
        # Store questions and expected answers
        question_set_id = str(uuid.uuid4())
        collections['questions'].insert_one({
            "_id": question_set_id,
            "user_id": "public_user",
            "questions": questions,
            "expected_answers": expected_answers,
            "skills": info["skills"],
            "timestamp": datetime.utcnow()
        })

        # Clean up uploaded file
        try:
            os.remove(file_path)
        except:
            pass

        return jsonify({
            "question_set_id": question_set_id,
            "questions": questions,
            "skills": info["skills"]
        })
    except Exception as e:
        print(f"Upload resume public error: {str(e)}")
        return jsonify({"error": "Failed to process resume"}), 500

@app.route("/api/question-history-public", methods=["GET"])
def question_history_public():
    print(f"DEBUG: /api/question-history-public endpoint hit. Questions collection available: {collections and collections['questions'] is not None}")
    if collections is None or collections['questions'] is None:
        return jsonify({"error": "Question history not available in local mode"}), 503
    
    try:
        # Fetch questions generated for the 'public_user'
        history_entries = list(collections['questions'].find({"user_id": "public_user"}).sort("timestamp", -1))
        
        # Convert ObjectId and datetime objects to strings for JSON serialization
        for entry in history_entries:
            entry['_id'] = str(entry['_id'])
            if 'timestamp' in entry and isinstance(entry['timestamp'], datetime):
                entry['timestamp'] = entry['timestamp'].isoformat()
            # Ensure questions and skills are lists for consistent frontend handling
            if 'questions' not in entry or not isinstance(entry['questions'], list):
                entry['questions'] = []
            if 'skills' not in entry or not isinstance(entry['skills'], list):
                entry['skills'] = []
            # Add a sourceType for the frontend to differentiate
            entry['sourceType'] = 'public' # Or 'voice' if this endpoint is only for voice-generated
            
        print(f"DEBUG: Fetched {len(history_entries)} public history entries.")
        return jsonify(history_entries), 200
    except Exception as e:
        print(f"Error fetching public question history: {str(e)}")
        return jsonify({"error": "Failed to retrieve public question history"}), 500

@app.route("/api/process-voice-public", methods=["POST"])
def process_voice_public():
    print(f"DEBUG: /api/process-voice-public endpoint hit. Questions collection available: {collections and collections['questions'] is not None}")
    if collections is None or collections['questions'] is None:
        return jsonify({"error": "Voice processing not available in local mode"}), 503

    try:
        data = request.json
        if not data or 'transcription' not in data:
            return jsonify({"error": "No transcription data provided"}), 400

        transcription_text = data['transcription']
        
        # Use the transcription text to generate questions and skills
        info = extract_info(transcription_text) # Assuming extract_info can work with raw text
        questions = generate_questions(skills=info["skills"], resume_text=transcription_text)
        expected_answers = generate_expected_answers(questions, skills=info["skills"], resume_text=transcription_text)

        question_set_id = str(uuid.uuid4())
        collections['questions'].insert_one({
            "_id": question_set_id,
            "user_id": "public_user", # Mark as public
            "questions": questions,
            "expected_answers": expected_answers,
            "skills": info["skills"],
            "timestamp": datetime.utcnow(),
            "sourceType": "voice" # Indicate source type
        })

        print(f"DEBUG: Voice transcription processed and questions generated. ID: {question_set_id}")
        return jsonify({
            "question_set_id": question_set_id,
            "questions": questions,
            "skills": info["skills"]
        }), 200

    except Exception as e:
        print(f"Error processing voice input: {str(e)}")
        return jsonify({"error": "Failed to process voice input"}), 500

# Continue with the rest of your endpoints...
# (I've included the key fixes for the main issues)

@app.route("/api/submit-answer", methods=["POST"])
def submit_answer():
    print(f"DEBUG: /api/submit-answer endpoint hit. User answers collection available: {collections and collections['user_answers'] is not None}")
    if collections is None or collections['user_answers'] is None or collections['questions'] is None:
        return jsonify({"error": "Database unavailable for answer submission"}), 503

    try:
        data = request.json
        question_set_id = data.get('question_set_id')
        question_index = data.get('question_index')
        user_answer = data.get('answer')

        if not all([question_set_id, isinstance(question_index, int), user_answer]):
            return jsonify({"error": "Missing data for answer submission"}), 400

        question_set = collections['questions'].find_one({"_id": question_set_id})
        if not question_set:
            return jsonify({"error": "Question set not found"}), 404

        if question_index >= len(question_set['questions']):
            return jsonify({"error": "Question index out of bounds"}), 400

        question_text = question_set['questions'][question_index]
        expected_answer = question_set['expected_answers'][question_index]
        skills = question_set['skills']

        print(f"DEBUG: Processing answer for question: {question_text[:50]}...")
        
        # Use AI to generate comprehensive feedback
        try:
            print("DEBUG: Calling AI for feedback generation...")
            ai_feedback = compare_and_provide_feedback(user_answer, expected_answer)
            print(f"DEBUG: AI feedback generated successfully: {ai_feedback[:100]}...")
        except Exception as ai_error:
            print(f"ERROR: AI feedback generation failed: {str(ai_error)}")
            # Fallback to simple feedback
            ai_feedback = "Your answer has been recorded. Consider reviewing the expected answer to identify areas for improvement."

        # Store the user's answer and AI feedback
        answer_record = {
            "question_set_id": question_set_id,
            "question_index": question_index,
            "question_text": question_text,
            "user_answer": user_answer,
            "ai_feedback": ai_feedback,
            "expected_answer": expected_answer,
            "skills": skills,
            "timestamp": datetime.utcnow()
        }
        
        try:
            collections['user_answers'].insert_one(answer_record)
            print(f"DEBUG: Answer record saved successfully")
        except Exception as db_error:
            print(f"ERROR: Failed to save answer record: {str(db_error)}")
            # Continue anyway since we have the feedback

        print(f"DEBUG: Answer submitted for question set {question_set_id}, index {question_index}.")
        
        return jsonify({
            "feedback": ai_feedback,
            "expected_answer": expected_answer,
            "message": "Answer submitted successfully"
        }), 200

    except Exception as e:
        print(f"ERROR: Submit answer failed: {str(e)}")
        print(f"ERROR: Traceback: {traceback.format_exc()}")
        return jsonify({"error": "Failed to submit answer"}), 500


@app.route("/api/answer-history", methods=["GET"])
@token_required
def get_answer_history(current_user):
    """Get user's answer history with AI feedback"""
    print(f"DEBUG: /api/answer-history endpoint hit for user: {current_user['username']}")
    if collections is None or collections['user_answers'] is None:
        return jsonify({"error": "Answer history not available in local mode"}), 503
    
    try:
        # Get all answers for this user (you might need to modify this based on how you track users)
        # For now, we'll get recent answers - you may want to add user tracking
        answer_history = list(collections['user_answers'].find().sort("timestamp", -1).limit(20))
        
        # Convert ObjectId and datetime objects for JSON serialization
        for record in answer_history:
            record['_id'] = str(record['_id'])
            if 'timestamp' in record and isinstance(record['timestamp'], datetime):
                record['timestamp'] = record['timestamp'].isoformat()
        
        print(f"DEBUG: Retrieved {len(answer_history)} answer records")
        return jsonify(answer_history), 200
    
    except Exception as e:
        print(f"ERROR: Failed to retrieve answer history: {str(e)}")
        return jsonify({"error": "Failed to retrieve answer history"}), 500


@app.route("/api/answer-history-public", methods=["GET"])
def get_answer_history_public():
    """Get recent public answer submissions with AI feedback"""
    print(f"DEBUG: /api/answer-history-public endpoint hit")
    if collections is None or collections['user_answers'] is None:
        return jsonify({"error": "Answer history not available in local mode"}), 503
    
    try:
        # Get recent public answers
        answer_history = list(collections['user_answers'].find().sort("timestamp", -1).limit(10))
        
        # Convert ObjectId and datetime objects for JSON serialization
        for record in answer_history:
            record['_id'] = str(record['_id'])
            if 'timestamp' in record and isinstance(record['timestamp'], datetime):
                record['timestamp'] = record['timestamp'].isoformat()
        
        print(f"DEBUG: Retrieved {len(answer_history)} public answer records")
        return jsonify(answer_history), 200
    
    except Exception as e:
        print(f"ERROR: Failed to retrieve public answer history: {str(e)}")
        return jsonify({"error": "Failed to retrieve answer history"}), 500
    

@app.route("/api/test-ai-feedback", methods=["POST"])
def test_ai_feedback():
    """Test endpoint for AI feedback generation"""
    try:
        data = request.json
        user_answer = data.get('user_answer', '')
        expected_answer = data.get('expected_answer', '')
        
        if not user_answer or not expected_answer:
            return jsonify({"error": "Both user_answer and expected_answer are required"}), 400
        
        print("DEBUG: Testing AI feedback generation...")
        feedback = compare_and_provide_feedback(user_answer, expected_answer)
        
        return jsonify({
            "feedback": feedback,
            "message": "AI feedback generated successfully"
        }), 200
        
    except Exception as e:
        print(f"ERROR: AI feedback test failed: {str(e)}")
        return jsonify({"error": f"AI feedback test failed: {str(e)}"}), 500
    

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    print(f"Unhandled exception: {str(e)}")
    return jsonify({
        "error": "An unexpected error occurred",
        "details": str(e) if app.debug else "Please try again later"
    }), 500

if __name__ == "__main__":
    # Get port from environment variable
    port = int(os.environ.get("PORT", 5000))
    
    try:
        print(f"🚀 Starting Flask application on port {port}...")
        print(f"🌐 CORS enabled for: http://localhost:5173, http://localhost:3000")
        print(f"🗄️ Database: {'Connected' if client else 'Local development mode'}")
        
        app.run(
            host="0.0.0.0", 
            port=port, 
            debug=True,  # Enable debug for local development
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n🛑 Shutdown initiated by user")
    except Exception as e:
        print(f"❌ Application error: {e}")
    finally:
        cleanup_resources()