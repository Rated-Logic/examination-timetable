from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

# Define routes for other pages
@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/student/profile')
def student_profile():
    return render_template('student_profile.html')


@app.route('/student/dashboard')
def student_dashboard():
    return render_template('student_dashboard.html')

@app.route('/invigilator/dashboard')
def invigilator_dashboard(): 
    return render_template('invigilator_dashboard.html')


@app.route('/invigilator/profile')
def invigilator_profile(): 
    return render_template('invigilator_profile.html')

@app.route('/admin/dashboard')
def admin_dashboard(): 
    return render_template('admin_dashboard.html')

@app.route('/admin/timetable')
def timetable(): 
    return render_template('timetable.html')

@app.route('/admin/venues')
def admin_venue(): 
    return render_template('venues.html')

@app.route('/admin/sessions')
def sessions(): 
    return render_template('sessions.html')

@app.route('/admin/time')
def time(): 
    return render_template('time.html')

@app.route('/admin/management')
def admin_user_management(): 
    return render_template('user_management.html')


@app.route('/admin/departments')
def departments(): 
    return render_template('departments.html')

# More routes will be added for each page...

if __name__ == '__main__':
    app.run(debug=True)
