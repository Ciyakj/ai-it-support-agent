"""
Mock IT Admin Panel - Flask application
Allows managing users, resetting passwords, and assigning licenses
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///admin_panel.db'
app.config['SECRET_KEY'] = 'dev-secret-key-12345'

db = SQLAlchemy(app)

# Global task status tracker
current_task = {
    "description": "",
    "status": "idle",  # idle, executing, completed
    "iterations": 0
}

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    status = db.Column(db.String(20), default='active')  # active, inactive, locked
    password = db.Column(db.String(255), default='TempPass123!')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    licenses = db.relationship('License', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.email}>'

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    license_type = db.Column(db.String(50))  # email, office365, slack, vpn
    status = db.Column(db.String(20), default='active')  # active, inactive
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

# Initialize database
with app.app_context():
    db.create_all()
    # Add some sample users if empty - KEEP EXACTLY 4
    if User.query.count() == 0:
        sample_users = [
            User(email='alice@company.com', first_name='Alice', last_name='Johnson', status='active'),
            User(email='bob@company.com', first_name='Bob', last_name='Smith', status='active'),
            User(email='charlie@company.com', first_name='Charlie', last_name='Brown', status='locked'),
            User(email='diana@company.com', first_name='Diana', last_name='Prince', status='active'),
        ]
        db.session.add_all(sample_users)
        db.session.commit()

# Routes
@app.route('/')
def dashboard():
    """Main dashboard page"""
    total_users = User.query.count()
    active_users = User.query.filter_by(status='active').count()
    licenses_count = License.query.count()
    return render_template('dashboard.html', 
                         total_users=total_users,
                         active_users=active_users,
                         licenses_count=licenses_count)

@app.route('/users')
def users_list():
    """List all users"""
    users = User.query.all()
    return render_template('users.html', users=users)

@app.route('/users/create', methods=['GET', 'POST'])
def create_user():
    """Create a new user"""
    if request.method == 'POST':
        email = request.form.get('email')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        
        # Check if user exists
        if User.query.filter_by(email=email).first():
            return render_template('create_user.html', error='User already exists')
        
        new_user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            status='active'
        )
        db.session.add(new_user)
        db.session.commit()
        
        return redirect(url_for('users_list'))
    
    return render_template('create_user.html')

@app.route('/users/<int:user_id>')
def user_detail(user_id):
    """View user details"""
    user = User.query.get_or_404(user_id)
    return render_template('user_detail.html', user=user)

@app.route('/users/<int:user_id>/reset-password', methods=['GET', 'POST'])
def reset_password(user_id):
    """Reset user password - form and submission"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Handle form submission
        new_password = request.form.get('new_password')
        
        if not new_password:
            return render_template('reset_password.html', user=user, error='Password cannot be empty')
        
        user.password = new_password
        user.status = 'active'
        db.session.commit()
        
        # Redirect to users list on success
        return redirect(url_for('users_list'))
    
    # Show form (GET request)
    return render_template('reset_password.html', user=user)

@app.route('/users/<int:user_id>/unlock', methods=['POST'])
def unlock_user(user_id):
    """Unlock a locked user account"""
    user = User.query.get_or_404(user_id)
    user.status = 'active'
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'User {user.email} unlocked'
    })

@app.route('/users/<int:user_id>/deactivate', methods=['POST'])
def deactivate_user(user_id):
    """Deactivate a user"""
    user = User.query.get_or_404(user_id)
    user.status = 'inactive'
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'User {user.email} deactivated'
    })

# @app.route('/licenses')
# def licenses_list():
#     """List all licenses"""
#     licenses = License.query.all()
#     users = User.query.all()
#     return render_template('licenses.html', licenses=licenses, users=users)

# @app.route('/licenses/assign', methods=['GET', 'POST'])
# def assign_license():
#     """Assign license to user"""
#     if request.method == 'POST':
#         user_id = request.form.get('user_id')
#         license_type = request.form.get('license_type')
#         
#         user = User.query.get_or_404(user_id)
#         
#         # Check if already assigned
#         existing = License.query.filter_by(user_id=user_id, license_type=license_type).first()
#         if existing and existing.status == 'active':
#             return render_template('assign_license.html', 
#                                   users=User.query.all(),
#                                   error=f'{license_type} already assigned to this user')
#         
#         license_obj = License(user_id=user_id, license_type=license_type, status='active')
#         db.session.add(license_obj)
#         db.session.commit()
#         
#         return redirect(url_for('licenses_list'))
#     
#     return render_template('assign_license.html', users=User.query.all())

@app.route('/api/users/<email>')
def api_user_by_email(email):
    """API endpoint to get user by email"""
    user = User.query.filter_by(email=email).first()
    if user:
        return jsonify({
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'status': user.status
        })
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/task/set', methods=['POST'])
def set_task_status():
    """Set current task status (for agent to call)"""
    global current_task
    data = request.get_json()
    current_task['description'] = data.get('description', '')
    current_task['status'] = data.get('status', 'executing')
    current_task['iterations'] = data.get('iterations', 0)
    return jsonify({'success': True})

@app.route('/api/task/get')
def get_task_status():
    """Get current task status (for UI to display)"""
    global current_task
    return jsonify(current_task)

def initialize_db():
    """Initialize the database"""
    with app.app_context():
        db.create_all()

if __name__ == '__main__':
    initialize_db()
    app.run(debug=True, port=5000)
