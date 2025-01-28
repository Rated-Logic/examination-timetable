from flask import Flask
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash
from datetime import datetime

app = Flask(__name__)
app.config["MONGO_URI"] = "mongodb://localhost:27017/exam_scheduler"
mongo = PyMongo(app)

def init_admin():
    # Check if admin already exists
    existing_admin = mongo.db.users.find_one({"email": "ratedlogic@gmail.com"})
    
    if not existing_admin:
        admin_user = {
            "email": "ratedlogic@gmail.com",
            "password": generate_password_hash("stephy360"),
            "role": "admin",
            "created_at": datetime.utcnow(),
            "last_login": None
        }
        
        mongo.db.users.insert_one(admin_user)
        print("Default admin user created successfully!")
    else:
        print("Admin user already exists!")

if __name__ == "__main__":
    init_admin() 