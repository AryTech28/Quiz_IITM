from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secret key for session management

# Function to update database schema if needed
def update_db_schema():
    conn = sqlite3.connect('quiz_master.db')
    cursor = conn.cursor()
    
    # Check if columns exist and add them if they don't
    try:
        cursor.execute("SELECT fullname FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN fullname TEXT DEFAULT 'User'")
    
    try:
        cursor.execute("SELECT qualification FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN qualification TEXT DEFAULT 'Not specified'")
    
    try:
        cursor.execute("SELECT dob FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN dob TEXT DEFAULT '2000-01-01'")
    
    # Create subjects and chapters tables if they don't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        FOREIGN KEY (subject_id) REFERENCES subjects (id),
        UNIQUE(subject_id, name)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chapter_id INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        option_a TEXT NOT NULL,
        option_b TEXT NOT NULL,
        option_c TEXT NOT NULL,
        option_d TEXT NOT NULL,
        correct_answer TEXT NOT NULL,
        FOREIGN KEY (chapter_id) REFERENCES chapters (id)
    )
    ''')
    
    # Insert default subjects and chapters if none exist
    cursor.execute("SELECT COUNT(*) FROM subjects")
    if cursor.fetchone()[0] == 0:
        # Add Physics subject
        cursor.execute("INSERT INTO subjects (name) VALUES (?)", ("Physics",))
        physics_id = cursor.lastrowid
        cursor.execute("INSERT INTO chapters (subject_id, name) VALUES (?, ?)", (physics_id, "Force"))
        cursor.execute("INSERT INTO chapters (subject_id, name) VALUES (?, ?)", (physics_id, "EMF"))
        
        # Add App Dev-I subject
        cursor.execute("INSERT INTO subjects (name) VALUES (?)", ("App Dev-I",))
        appdev_id = cursor.lastrowid
        cursor.execute("INSERT INTO chapters (subject_id, name) VALUES (?, ?)", (appdev_id, "HTML"))
        cursor.execute("INSERT INTO chapters (subject_id, name) VALUES (?, ?)", (appdev_id, "CSS"))
    
    conn.commit()
    conn.close()

# Database setup
def init_db():
    conn = sqlite3.connect('quiz_master.db')
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        fullname TEXT NOT NULL,
        qualification TEXT NOT NULL,
        dob TEXT NOT NULL,
        is_admin BOOLEAN NOT NULL DEFAULT 0
    )
    ''')
    
    # Check if admin exists, if not create one
    cursor.execute("SELECT * FROM users WHERE is_admin = 1")
    admin = cursor.fetchone()
    
    if not admin:
        # Create admin user (email: admin@quizmaster.com, password: adminpass)
        admin_password = generate_password_hash('adminpass')
        cursor.execute("INSERT INTO users (email, password, fullname, qualification, dob, is_admin) VALUES (?, ?, ?, ?, ?, ?)",
                      ('admin@quizmaster.com', admin_password, 'Admin User', 'Administrator', '1990-01-01', 1))
    
    conn.commit()
    conn.close()

# Initialize database on startup
update_db_schema()  # Add this first to update existing databases
init_db()

# Helper function to get subjects and their chapters
def get_subjects_with_chapters():
    conn = sqlite3.connect('quiz_master.db')
    conn.row_factory = sqlite3.Row  # This enables column access by name
    cursor = conn.cursor()
    
    subjects = []
    cursor.execute("SELECT id, name FROM subjects ORDER BY name")
    for subject in cursor.fetchall():
        subject_dict = dict(subject)
        subject_dict['chapters'] = []
        
        # Get chapters for this subject
        cursor.execute("""
            SELECT c.id, c.name, COUNT(q.id) as question_count 
            FROM chapters c 
            LEFT JOIN questions q ON c.id = q.chapter_id
            WHERE c.subject_id = ?
            GROUP BY c.id
            ORDER BY c.name
        """, (subject['id'],))
        
        for chapter in cursor.fetchall():
            subject_dict['chapters'].append(dict(chapter))
        
        subjects.append(subject_dict)
    
    conn.close()
    return subjects

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    
    if request.method == 'POST':
        email = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('quiz_master.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        
        if user and check_password_hash(user[2], password):
            # Store user info in session
            session['user_id'] = user[0]
            session['email'] = user[1]
            session['fullname'] = user[3]
            session['is_admin'] = user[6]
            
            if user[6]:  # If admin
                return redirect(url_for('admin_dashboard'))
            else:  # If regular user
                return redirect(url_for('user_dashboard'))
        else:
            error = "Invalid username or password"
        
        conn.close()
    
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    success = None
    
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        fullname = request.form['fullname']
        qualification = request.form['qualification']
        dob = request.form['dob']
        
        # Basic validation
        if not all([email, password, fullname, qualification, dob]):
            error = "All fields are required"
        else:
            try:
                conn = sqlite3.connect('quiz_master.db')
                cursor = conn.cursor()
                
                # Check if email already exists
                cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
                if cursor.fetchone():
                    error = "Email already registered"
                else:
                    # Hash the password before storing
                    hashed_password = generate_password_hash(password)
                    
                    # Insert new user
                    cursor.execute("INSERT INTO users (email, password, fullname, qualification, dob, is_admin) VALUES (?, ?, ?, ?, ?, ?)",
                                  (email, hashed_password, fullname, qualification, dob, 0))
                    
                    conn.commit()
                    success = "Registration successful! You can now log in."
                
                conn.close()
                
                # If registration is successful, redirect to login after a delay
                if success:
                    return render_template('register.html', success=success)
            
            except Exception as e:
                error = f"An error occurred: {str(e)}"
    
    return render_template('register.html', error=error, success=success)

@app.route('/admin-dashboard')
def admin_dashboard():
    # Ensure user is logged in and is an admin
    if not session.get('user_id') or not session.get('is_admin'):
        return redirect(url_for('login'))
    
    # Get subjects and chapters
    subjects = get_subjects_with_chapters()
    
    return render_template('admin_dashboard.html', subjects=subjects)

@app.route('/user-dashboard')
def user_dashboard():
    # Ensure user is logged in
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    # Placeholder for user dashboard
    return "User Dashboard"

@app.route('/add-subject', methods=['GET', 'POST'])
def add_subject():
    # Ensure user is logged in and is an admin
    if not session.get('user_id') or not session.get('is_admin'):
        return redirect(url_for('login'))
    
    error = None
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        
        # Basic validation
        if not name:
            error = "Subject name is required"
        else:
            try:
                conn = sqlite3.connect('quiz_master.db')
                cursor = conn.cursor()
                
                # Check if subject already exists
                cursor.execute("SELECT * FROM subjects WHERE name = ?", (name,))
                if cursor.fetchone():
                    error = "Subject with this name already exists"
                else:
                    # Insert new subject
                    cursor.execute("INSERT INTO subjects (name, description) VALUES (?, ?)",
                                  (name, description))
                    
                    conn.commit()
                    
                    # Redirect to admin dashboard on success
                    return redirect(url_for('admin_dashboard'))
                
                conn.close()
            
            except Exception as e:
                error = f"An error occurred: {str(e)}"
    
    return render_template('add_subject.html', error=error)

@app.route('/add-chapter/<int:subject_id>', methods=['GET', 'POST'])
def add_chapter(subject_id):
    # Ensure user is logged in and is an admin
    if not session.get('user_id') or not session.get('is_admin'):
        return redirect(url_for('login'))
    
    error = None
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        
        # Basic validation
        if not name:
            error = "Chapter name is required"
        else:
            try:
                conn = sqlite3.connect('quiz_master.db')
                cursor = conn.cursor()
                
                # Check if chapter already exists in this subject
                cursor.execute("SELECT * FROM chapters WHERE subject_id = ? AND name = ?", 
                              (subject_id, name))
                if cursor.fetchone():
                    error = "Chapter with this name already exists in this subject"
                else:
                    # Insert new chapter
                    cursor.execute("INSERT INTO chapters (subject_id, name, description) VALUES (?, ?, ?)",
                                  (subject_id, name, description))
                    
                    conn.commit()
                    
                    # Redirect to admin dashboard on success
                    return redirect(url_for('admin_dashboard'))
                
                conn.close()
            
            except Exception as e:
                error = f"An error occurred: {str(e)}"
    
    return render_template('add_chapter.html', error=error, subject_id=subject_id)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)