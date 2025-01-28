from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_pymongo import PyMongo
from models import mongo
from bson import ObjectId
from datetime import datetime, timedelta
import os
from werkzeug.security import check_password_hash, generate_password_hash
import random

app = Flask(__name__)
app.config["MONGO_URI"] = "mongodb://localhost:27017/exam_scheduler"
app.config['SECRET_KEY'] = os.urandom(24)
mongo.init_app(app)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/timetable/generate', methods=['POST'])
def generate_timetable():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
    end_date = datetime.strptime(data['end_date'], '%Y-%m-%d')
    
    try:
        # Get and validate required data
        venues = list(mongo.db.venues.find())
        if not venues:
            return jsonify({'error': 'No venues available'}), 400
            
        sessions = list(mongo.db.sessions.find())
        if not sessions:
            return jsonify({'error': 'No sessions available'}), 400
            
        departments = list(mongo.db.departments.find())
        if not departments:
            return jsonify({'error': 'No departments available'}), 400
            
        invigilators = list(mongo.db.users.find({'role': 'invigilator'}))
        if not invigilators:
            return jsonify({'error': 'No invigilators available'}), 400

        # Convert ObjectIds to strings
        for venue in venues:
            venue['_id'] = str(venue['_id'])
        for session_data in sessions:
            session_data['_id'] = str(session_data['_id'])
        for dept in departments:
            dept['_id'] = str(dept['_id'])
        for invigilator in invigilators:
            invigilator['_id'] = str(invigilator['_id'])
        
        # Initialize tracking sets
        timetable = []
        completed_modules = set()  # Track completed modules
        course_daily_count = {}  # Track modules per course per day
        course_session_used = set()  # Track course-session combinations
        
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5:  # Monday to Friday only
                date_str = current_date.strftime('%Y-%m-%d')
                course_daily_count[date_str] = {}  # Reset daily count for each date
                
                for session_slot in sessions:
                    used_venues = set()
                    used_invigilators = set()
                    
                    # Randomize departments and courses
                    shuffled_depts = list(departments)
                    random.shuffle(shuffled_depts)
                    
                    for dept in shuffled_depts:
                        shuffled_courses = list(dept.get('courses', []))
                        random.shuffle(shuffled_courses)
                        
                        for course in shuffled_courses:
                            course_id = f"{dept.get('name')}_{course.get('name')}"
                            
                            # Skip if course already has a module in this session
                            session_key = f"{date_str}_{session_slot.get('name')}_{course_id}"
                            if session_key in course_session_used:
                                continue
                                
                            # Skip if course has reached daily limit (changed to 2)
                            if course_daily_count.get(date_str, {}).get(course_id, 0) >= 2:
                                print(f"Course {course_id} has reached daily limit on {date_str}")
                                continue
                            
                            # Handle modules
                            modules = course.get('modules', [])
                            if isinstance(modules, str):
                                modules = [{'name': modules}]
                            elif isinstance(modules, list):
                                modules = [{'name': m} if isinstance(m, str) else m for m in modules]
                            
                            # Filter out completed modules
                            available_modules = [
                                m for m in modules 
                                if isinstance(m, dict) and 
                                'name' in m and 
                                f"{course_id}_{m['name']}" not in completed_modules
                            ]
                            
                            if not available_modules:
                                continue
                            
                            # Randomly select a module
                            module = random.choice(available_modules)
                            
                            # Find available venue
                            available_venue = next(
                                (v for v in venues 
                                 if v['_id'] not in used_venues 
                                 and v['capacity'] >= course.get('student_count', 0)), 
                                None
                            )
                            
                            if not available_venue:
                                continue
                                
                            # Find available invigilator
                            available_invigilator = next(
                                (i for i in invigilators 
                                 if i['_id'] not in used_invigilators),
                                None
                            )
                            
                            if not available_invigilator:
                                continue
                            
                            # Create exam slot
                            exam_slot = {
                                'date': date_str,
                                'session_name': session_slot.get('name', ''),
                                'start_time': session_slot.get('start_time', ''),
                                'end_time': session_slot.get('end_time', ''),
                                'department': dept.get('name', ''),
                                'course_name': course.get('name', ''),
                                'course_level': course.get('level', ''),
                                'course_year': course.get('year', ''),
                                'module_name': module['name'],
                                'venue': available_venue.get('name', ''),
                                'venue_id': ObjectId(available_venue['_id']),
                                'invigilator': available_invigilator.get('full_name', ''),
                                'invigilator_id': ObjectId(available_invigilator['_id']),
                                'student_count': course.get('student_count', 0)
                            }
                            
                            # Update tracking information
                            completed_modules.add(f"{course_id}_{module['name']}")
                            course_session_used.add(session_key)
                            course_daily_count[date_str][course_id] = course_daily_count[date_str].get(course_id, 0) + 1
                            
                            used_venues.add(available_venue['_id'])
                            used_invigilators.add(available_invigilator['_id'])
                            
                            timetable.append(exam_slot)
                            print(f"Added exam slot for {course_id} - {module['name']} on {date_str} (Daily count: {course_daily_count[date_str][course_id]})")
                            
            current_date += timedelta(days=1)
        
        # Save and return timetable
        if timetable:
            mongo.db.timetable.delete_many({})
            result = mongo.db.timetable.insert_many(timetable)
            
            for slot in timetable:
                slot['_id'] = str(slot['_id'])
                slot['venue_id'] = str(slot['venue_id'])
                slot['invigilator_id'] = str(slot['invigilator_id'])
                
            return jsonify({'message': 'Timetable generated successfully', 'timetable': timetable})
        else:
            print("No timetable slots were generated")
            return jsonify({'error': 'Could not generate timetable. Please check if you have venues, sessions, courses with modules, and invigilators available.'}), 400
            
    except Exception as e:
        print(f"Error generating timetable: {str(e)}")
        return jsonify({'error': f'Error generating timetable: {str(e)}'}), 500

@app.route('/api/admin/timetable', methods=['GET'])
def get_admin_timetable():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        timetable = list(mongo.db.timetable.find())
        # Convert ObjectIds to strings for JSON response
        for slot in timetable:
            slot['_id'] = str(slot['_id'])
            slot['venue_id'] = str(slot['venue_id'])
            slot['invigilator_id'] = str(slot['invigilator_id'])
        return jsonify(timetable)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/student/timetable')
def get_student_timetable():
    if not session.get('user_id') or session.get('role') != 'student':
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        student = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
        if not student:
            session.clear()  # Clear invalid session
            return jsonify({'error': 'Unauthorized'}), 403

        # Get timetable entries for student's course
        timetable = list(mongo.db.timetable.find({
            'course_name': student['course'],
            'course_level': student['level'],
            'course_year': student['year']
        }).sort('date', 1))

        # Convert ObjectIds to strings
        for entry in timetable:
            entry['_id'] = str(entry['_id'])
            if 'venue_id' in entry:
                entry['venue_id'] = str(entry['venue_id'])
            if 'invigilator_id' in entry:
                entry['invigilator_id'] = str(entry['invigilator_id'])

        return jsonify(timetable)
    except Exception as e:
        print(f"Error fetching student timetable: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/invigilator/timetable')
def get_invigilator_timetable():
    if not session.get('user_id') or session.get('role') != 'invigilator':
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        invigilator = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
        if not invigilator:
            session.clear()
            return jsonify({'error': 'Unauthorized'}), 403

        # Get timetable entries where this invigilator is assigned
        timetable = list(mongo.db.timetable.find({
            'invigilator_id': ObjectId(session['user_id'])
        }).sort('date', 1))

        # Convert ObjectIds to strings
        for entry in timetable:
            entry['_id'] = str(entry['_id'])
            entry['venue_id'] = str(entry['venue_id'])
            entry['invigilator_id'] = str(entry['invigilator_id'])

        return jsonify(timetable)
    except Exception as e:
        print(f"Error fetching invigilator timetable: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/invigilator')
def invigilator_dashboard():
    if not session.get('user_id') or session.get('role') != 'invigilator':
        return redirect('/login')
    return render_template('invigilator_dashboard.html')

@app.route('/invigilator/profile')
def invigilator_profile():
    if not session.get('user_id') or session.get('role') != 'invigilator':
        return redirect('/login')
    return render_template('invigilator_profile.html')

@app.route('/api/invigilator/profile')
def get_invigilator_profile():
    if not session.get('user_id') or session.get('role') != 'invigilator':
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        invigilator = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
        if not invigilator:
            session.clear()
            return jsonify({'error': 'Unauthorized'}), 403

        profile_data = {
            'full_name': invigilator.get('full_name', ''),
            'email': invigilator.get('email', ''),
            'department_name': invigilator.get('department_name', ''),
            'role': 'Invigilator'
        }
            
        return jsonify(profile_data)
    except Exception as e:
        print(f"Error fetching invigilator profile: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
        
    data = request.get_json()
    user = mongo.db.users.find_one({"email": data['email']})
    
    if user and check_password_hash(user['password'], data['password']):
        session['user_id'] = str(user['_id'])
        session['role'] = user['role']
        return jsonify({
            "message": "Login successful",
            "role": user['role']
        })
    
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
        
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['email', 'full_name', 'role', 'department', 'password']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    # Check if email already exists
    if mongo.db.users.find_one({"email": data['email']}):
        return jsonify({"error": "Email already registered"}), 400
    
    # Get department details
    department = mongo.db.departments.find_one({"_id": ObjectId(data['department'])})
    if not department:
        return jsonify({"error": "Invalid department"}), 400
    
    # Create user document
    user_data = {
        "email": data['email'],
        "full_name": data['full_name'],
        "role": data['role'],
        "department_id": ObjectId(data['department']),
        "department_name": department['name'],
        "password": generate_password_hash(data['password']),
        "created_at": datetime.utcnow()
    }
    
    # Add course, level, and year for students
    if data['role'] == 'student':
        if not all(field in data for field in ['course', 'level', 'year']):
            return jsonify({"error": "Course, level, and year required for students"}), 400
        user_data.update({
            "course": data['course'],
            "level": data['level'],
            "year": data['year']
        })
    
    try:
        mongo.db.users.insert_one(user_data)
        return jsonify({"message": "Registration successful"})
    except Exception as e:
        print(f"Registration error: {str(e)}")
        return jsonify({"error": "Registration failed. Please try again."}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    # Clear the session
    session.clear()
    return jsonify({"message": "Logged out successfully"})

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    user = mongo.db.users.find_one({"email": data['email']})
    
    if user and user['role'] == 'admin' and check_password_hash(user['password'], data['password']):
        session['user_id'] = str(user['_id'])
        session['role'] = 'admin'
        return jsonify({"message": "Login successful"})
    
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/admin/users', methods=['GET'])
def get_users():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    users = list(mongo.db.users.find(
        {"role": {"$ne": "admin"}},
        {"password": 0}
    ))

    # Convert ObjectId to string for all users
    for user in users:
        user['_id'] = str(user['_id'])
        if 'department_id' in user:
            user['department_id'] = str(user['department_id'])
    
    return jsonify(users)

@app.route('/api/admin/users', methods=['POST'])
def create_user():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    
    # Get department details
    department = mongo.db.departments.find_one({"_id": ObjectId(data['department'])})
    if not department:
        return jsonify({"error": "Invalid department"}), 400
    
    user_data = {
        "email": data['email'],
        "full_name": data['full_name'],
        "role": data['role'],
        "department_id": ObjectId(data['department']),
        "department_name": department['name'],
        "password": generate_password_hash(data['password']),
        "created_at": datetime.utcnow()
    }
    
    # Add student-specific fields if role is student
    if data['role'] == 'student':
        if not all(field in data for field in ['course', 'level', 'year']):
            return jsonify({"error": "Course, level, and year required for students"}), 400
        user_data.update({
            "course": data['course'],
            "level": data['level'],
            "year": data['year']
        })
    
    try:
        mongo.db.users.insert_one(user_data)
        return jsonify({"message": "User created successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    mongo.db.users.delete_one({"_id": ObjectId(user_id)})
    return jsonify({"message": "User deleted successfully"})

@app.route('/api/admin/stats', methods=['GET'])
def get_stats():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    # Get basic stats
    stats = {
        "total_students": mongo.db.users.count_documents({"role": "student"}),
        "total_invigilators": mongo.db.users.count_documents({"role": "invigilator"}),
        "total_venues": mongo.db.venues.count_documents({}),
        "upcoming_exams": 0,  # Will be set based on timetable count
        "next_exams": []  # Will hold the next 5 upcoming exams
    }
    
    try:
        # Get current date at midnight for accurate comparison
        current_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get upcoming exams from timetable
        upcoming_exams = list(mongo.db.timetable.find({
            "date": {"$gte": current_date.strftime('%Y-%m-%d')}
        }).sort("date", 1).limit(5))
        
        # Set upcoming exams count
        stats["upcoming_exams"] = len(upcoming_exams)
        
        # Format exam details for display
        for exam in upcoming_exams:
            exam_date = datetime.strptime(exam['date'], '%Y-%m-%d')
            stats["next_exams"].append({
                "date": exam_date.strftime('%d/%m/%Y'),
                "time": f"{exam['start_time']} - {exam['end_time']}",
                "course": exam['course_name'],
                "module": exam['module_name'],
                "venue": exam['venue'],
                "invigilator": exam['invigilator']
            })
        
        return jsonify(stats)
    except Exception as e:
        print(f"Error getting stats: {str(e)}")
        return jsonify({"error": "Error fetching statistics"}), 500

@app.route('/api/admin/venues', methods=['GET'])
def get_venues():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    venues = list(mongo.db.venues.find())
    return jsonify([{**venue, '_id': str(venue['_id'])} for venue in venues])

@app.route('/api/admin/venues', methods=['POST'])
def create_venue():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['name', 'capacity', 'block']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    # Validate capacity is a positive number
    try:
        capacity = int(data['capacity'])
        if capacity <= 0:
            return jsonify({"error": "Capacity must be a positive number"}), 400
        data['capacity'] = capacity
    except ValueError:
        return jsonify({"error": "Capacity must be a number"}), 400
    
    try:
        result = mongo.db.venues.insert_one(data)
        return jsonify({
            "message": "Venue created successfully",
            "id": str(result.inserted_id)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/venues/<venue_id>', methods=['PUT'])
def update_venue(venue_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['name', 'capacity', 'block']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    # Validate capacity is a positive number
    try:
        capacity = int(data['capacity'])
        if capacity <= 0:
            return jsonify({"error": "Capacity must be a positive number"}), 400
        data['capacity'] = capacity
    except ValueError:
        return jsonify({"error": "Capacity must be a number"}), 400
    
    try:
        mongo.db.venues.update_one(
            {"_id": ObjectId(venue_id)},
            {"$set": data}
        )
        return jsonify({"message": "Venue updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/venues/<venue_id>', methods=['DELETE'])
def delete_venue(venue_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        # Check if venue is being used in any exams
        if mongo.db.exams.find_one({"venue_id": ObjectId(venue_id)}):
            return jsonify({"error": "Cannot delete venue that is being used in exams"}), 400
        
        mongo.db.venues.delete_one({"_id": ObjectId(venue_id)})
        return jsonify({"message": "Venue deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/student')
def student_dashboard():
    if not session.get('user_id') or session.get('role') != 'student':
        return redirect('/login')
    return render_template('student_dashboard.html')

@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template('admin_dashboard.html')

@app.route('/login')
def login_page():
    # If user is already logged in, clear their session
    if session.get('user_id'):
        session.clear()
    return render_template('login.html')

@app.route('/register')
def register_page():
    if session.get('user_id'):
        role = session.get('role')
        return redirect(f'/{role}')
    return render_template('register.html')

@app.route('/admin/users')
def admin_user_management():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template('admin_user_management.html')

@app.route('/admin/venues')
def admin_venue():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template('admin_venue.html')

@app.route('/admin/sessions')
def sessions():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template('sessions.html')

@app.route('/api/admin/sessions', methods=['GET'])
def get_sessions():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    sessions = list(mongo.db.sessions.find())
    return jsonify([{**s, '_id': str(s['_id'])} for s in sessions])

@app.route('/api/admin/sessions', methods=['POST'])
def create_session():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['name', 'start_time', 'end_time']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    # Validate time format and logic
    try:
        start_time = datetime.strptime(data['start_time'], '%H:%M').time()
        end_time = datetime.strptime(data['end_time'], '%H:%M').time()
        
        if end_time <= start_time:
            return jsonify({"error": "End time must be after start time"}), 400
            
        # Store times as strings in HH:MM format
        data['start_time'] = start_time.strftime('%H:%M')
        data['end_time'] = end_time.strftime('%H:%M')
        
    except ValueError:
        return jsonify({"error": "Invalid time format. Use HH:MM"}), 400
    
    try:
        result = mongo.db.sessions.insert_one(data)
        return jsonify({
            "message": "Session created successfully",
            "id": str(result.inserted_id)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        session_data = mongo.db.sessions.find_one({"_id": ObjectId(session_id)})
        if not session_data:
            return jsonify({"error": "Session not found"}), 404
            
        session_data['_id'] = str(session_data['_id'])
        return jsonify(session_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/sessions/<session_id>', methods=['PUT'])
def update_session(session_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['name', 'start_time', 'end_time']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    # Validate time format and logic
    try:
        start_time = datetime.strptime(data['start_time'], '%H:%M').time()
        end_time = datetime.strptime(data['end_time'], '%H:%M').time()
        
        if end_time <= start_time:
            return jsonify({"error": "End time must be after start time"}), 400
            
        # Store times as strings in HH:MM format
        data['start_time'] = start_time.strftime('%H:%M')
        data['end_time'] = end_time.strftime('%H:%M')
        
    except ValueError:
        return jsonify({"error": "Invalid time format. Use HH:MM"}), 400
    
    try:
        mongo.db.sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": data}
        )
        return jsonify({"message": "Session updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        # Check if session is being used in any exams
        if mongo.db.exams.find_one({"session_id": ObjectId(session_id)}):
            return jsonify({"error": "Cannot delete session that is being used in exams"}), 400
        
        mongo.db.sessions.delete_one({"_id": ObjectId(session_id)})
        return jsonify({"message": "Session deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/time')
def time():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template('time.html')

@app.route('/api/admin/time', methods=['GET'])
def get_time_slots():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    time_slots = list(mongo.db.sessions.find({}, {
        'start_time': 1, 
        'end_time': 1, 
        'name': 1
    }))
    return jsonify([{**slot, '_id': str(slot['_id'])} for slot in time_slots])

@app.route('/api/admin/time', methods=['POST'])
def create_time_slot():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    mongo.db.sessions.insert_one(data)
    return jsonify({"message": "Time slot created successfully"})

@app.route('/api/admin/time/<slot_id>', methods=['DELETE'])
def delete_time_slot(slot_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    mongo.db.sessions.delete_one({"_id": ObjectId(slot_id)})
    return jsonify({"message": "Time slot deleted successfully"})

@app.route('/timetable')
def timetable():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template('timetable.html')

@app.route('/admin/timetable')
def admin_timetable():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template('timetable.html')

@app.route('/api/admin/timetable', methods=['GET'])
def get_timetable():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    exams = list(mongo.db.exams.aggregate([
        {
            '$lookup': {
                'from': 'venues',
                'localField': 'venue_id',
                'foreignField': '_id',
                'as': 'venue'
            }
        },
        {
            '$lookup': {
                'from': 'sessions',
                'localField': 'session_id',
                'foreignField': '_id',
                'as': 'session'
            }
        },
        {
            '$lookup': {
                'from': 'courses',
                'localField': 'course_id',
                'foreignField': '_id',
                'as': 'course'
            }
        },
        {
            '$project': {
                'date': 1,
                'module': 1,
                'venue_name': { '$arrayElemAt': ['$venue.name', 0] },
                'session_name': { '$arrayElemAt': ['$session.name', 0] },
                'session_time': {
                    '$concat': [
                        { '$arrayElemAt': ['$session.start_time', 0] },
                        ' - ',
                        { '$arrayElemAt': ['$session.end_time', 0] }
                    ]
                },
                'course_name': { '$arrayElemAt': ['$course.name', 0] }
            }
        },
        {
            '$sort': { 'date': 1 }
        }
    ]))
    
    return jsonify([{**exam, '_id': str(exam['_id'])} for exam in exams])

@app.route('/departments')
def departments():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template('departments.html')

@app.route('/admin/departments')
def admin_departments():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template('departments.html')

@app.route('/api/admin/departments', methods=['GET'])
def get_departments():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    departments = list(mongo.db.departments.find())
    return jsonify([{**dept, '_id': str(dept['_id'])} for dept in departments])

@app.route('/api/admin/departments', methods=['POST'])
def create_department():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    if not data.get('name'):
        return jsonify({"error": "Department name is required"}), 400
        
    mongo.db.departments.insert_one(data)
    return jsonify({"message": "Department created successfully"})

@app.route('/api/admin/departments/<dept_id>', methods=['GET'])
def get_department(dept_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    department = mongo.db.departments.find_one({"_id": ObjectId(dept_id)})
    if not department:
        return jsonify({"error": "Department not found"}), 404
        
    department['_id'] = str(department['_id'])
    return jsonify(department)

@app.route('/api/admin/departments/<dept_id>', methods=['PUT'])
def update_department(dept_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    if not data.get('name'):
        return jsonify({"error": "Department name is required"}), 400
    
    try:
        mongo.db.departments.update_one(
            {"_id": ObjectId(dept_id)},
            {"$set": {
                "name": data['name'],
                "courses": data['courses']
            }}
        )
        return jsonify({"message": "Department updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/departments/<dept_id>', methods=['DELETE'])
def delete_department(dept_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    # Check if department has associated users
    if mongo.db.users.find_one({"department_id": ObjectId(dept_id)}):
        return jsonify({"error": "Cannot delete department with associated users"}), 400
    
    mongo.db.departments.delete_one({"_id": ObjectId(dept_id)})
    return jsonify({"message": "Department deleted successfully"})

@app.route('/api/admin/departments/courses', methods=['POST'])
def add_department_with_courses():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    
    # Create department
    department_data = {
        "name": data['department_name'],
        "courses": []
    }
    
    # Add courses with their modules, level, and year
    for course in data['courses']:
        course_data = {
            "name": course['name'],
            "student_count": course['student_count'],
            "level": course['level'],
            "year": course['year'],
            "modules": course['modules']
        }
        department_data['courses'].append(course_data)
    
    try:
        mongo.db.departments.insert_one(department_data)
        return jsonify({"message": "Department and courses added successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/departments/<dept_id>/courses', methods=['GET'])
def get_department_courses(dept_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    department = mongo.db.departments.find_one({"_id": ObjectId(dept_id)})
    if not department:
        return jsonify({"error": "Department not found"}), 404
        
    return jsonify({
        "department_name": department['name'],
        "courses": department['courses']
    })

@app.route('/api/departments', methods=['GET'])
def get_all_departments():
    try:
        departments = list(mongo.db.departments.find({}, {"name": 1}))
        return jsonify([{
            "_id": str(dept["_id"]), 
            "name": dept["name"]
        } for dept in departments])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/departments/<dept_id>/courses', methods=['GET'])
def get_department_courses_public(dept_id):
    try:
        department = mongo.db.departments.find_one({"_id": ObjectId(dept_id)})
        if not department:
            return jsonify({"error": "Department not found"}), 404
            
        return jsonify({
            "department_name": department['name'],
            "courses": department['courses']
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/users/<user_id>', methods=['GET'])
def get_user(user_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Convert ObjectId fields to strings
        user['_id'] = str(user['_id'])
        if 'department_id' in user:
            user['department_id'] = str(user['department_id'])
            
        return jsonify(user)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/users/<user_id>', methods=['PUT'])
def update_user(user_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    
    try:
    # Get department details
        department = mongo.db.departments.find_one({"_id": ObjectId(data['department'])})
        if not department:
            return jsonify({"error": "Invalid department"}), 400
    
        update_data = {
        "email": data['email'],
        "full_name": data['full_name'],
        "department_id": ObjectId(data['department']),
        "department_name": department['name']
        }
    
    # Add student-specific fields if present
        if 'course' in data:
            update_data.update({
            "course": data['course'],
            "level": data['level'],
            "year": data['year']
        })
    
        mongo.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        return jsonify({"message": "User updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/venues/<venue_id>', methods=['GET'])
def get_venue(venue_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        venue = mongo.db.venues.find_one({"_id": ObjectId(venue_id)})
        if not venue:
            return jsonify({"error": "Venue not found"}), 404
            
        venue['_id'] = str(venue['_id'])
        return jsonify(venue)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/timetable', methods=['DELETE'])
def delete_timetable():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        mongo.db.timetable.delete_many({})
        return jsonify({'message': 'Timetable deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/timetable/<exam_id>', methods=['DELETE'])
def delete_exam_slot(exam_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        result = mongo.db.timetable.delete_one({'_id': ObjectId(exam_id)})
        if result.deleted_count:
            return jsonify({'message': 'Exam slot deleted successfully'})
        return jsonify({'error': 'Exam slot not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/student/profile')
def student_profile():
    if not session.get('user_id') or session.get('role') != 'student':
        return redirect('/login')
    return render_template('student_profile.html')

@app.route('/api/student/profile')
def get_student_profile():
    if not session.get('user_id') or session.get('role') != 'student':
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        student = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
        if not student:
            session.clear()  # Clear invalid session
            return jsonify({'error': 'Unauthorized'}), 403

        # Remove sensitive information and prepare response
        profile_data = {
            'full_name': student.get('full_name', ''),
            'email': student.get('email', ''),
            'department_name': student.get('department_name', ''),
            'course': student.get('course', ''),
            'level': student.get('level', ''),
            'year': student.get('year', '')
        }
            
        return jsonify(profile_data)
    except Exception as e:
        print(f"Error fetching student profile: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
