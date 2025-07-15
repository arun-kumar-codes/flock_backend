from firebase_admin import auth as firebase_auth
from flask import Blueprint, request, jsonify

from app import db
from app.models import User, UserRole, Invitation
from firebase_setup import *

auth_bp = Blueprint('auth', __name__)


# @auth_bp.route('/signup', methods=['POST'])
# def signup():
#     """User registration endpoint"""
#     try:
#         data = request.get_json()
        
#         if not data:
#             return jsonify({'error': 'No data provided'}), 400
        
#         # Validate required fields
#         username = data.get('username')
#         email = data.get('email')
#         password = data.get('password')
#         role = data.get('role', 'Viewer')
        
#         if not username or not email or not password:
#             return jsonify({'error': 'Username, email, and password are required'}), 400
        
        
#         # Validate role
#         valid_roles = [role.value for role in UserRole]
#         if role not in valid_roles:
#             return jsonify({'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}), 400
        
#         # Check if user already exists
#         if User.query.filter_by(username=username).first():
#             return jsonify({'error': 'Username already exists'}), 400
        
#         if User.query.filter_by(email=email).first():
#             return jsonify({'error': 'Email already exists'}), 400
        
#         # Create new user
#         user_role = UserRole(role)
#         user = User(
#             username=username,
#             email=email,
#             password=password,
#             role=user_role
#         )
        
#         db.session.add(user)
#         db.session.commit()
        
#         # Return response
#         response_data = {
#             'user': user.to_dict()
#         }
        
#         return jsonify(response_data), 201
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        id_token = request.json.get('idToken')
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get('email')

        # Check if user exists
        user = User.query.filter_by(email=email).first()
        if not user:
            invitation = Invitation.query.filter_by(email=email).first()
            if invitation:
                role = UserRole.CREATOR
            else:
                role = UserRole.VIEWER
            user = User(email=email, role=role)
            db.session.add(user)
            db.session.commit()

        profile_complete = user.is_profile_complete()
        
        return jsonify({
            'message': 'Login successful', 
            'user': user.to_dict(),
            'profile_complete': profile_complete
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 401
    
@auth_bp.route('/complete-profile', methods=['PUT'])
def complete_profile():
    try:
        id_token = request.json.get('idToken')
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get('email')
        
        username = request.json.get('username')
        password = request.json.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
            
        existing_user = User.query.filter_by(username=username).first()
        if existing_user and existing_user.email != email:
            return jsonify({'error': 'Username already exists'}), 400
            
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        user.update_profile(username, password)
        db.session.commit()
        
        return jsonify({
            'message': 'Profile completed successfully',
            'user': user.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    
@auth_bp.route('/login-password', methods=['POST'])
def login_password():
    """User login with password endpoint"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        identifier = data.get('username_or_email')
        password = data.get('password')
        
        if not identifier or not password:
            return jsonify({'error': 'Username/email and password are required'}), 400
        
        # Find user by username
        user = User.query.filter_by(email=identifier).first()
        if not user:
            user = User.query.filter_by(username=identifier).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid username/email or password'}), 400
        
        profile_complete = user.is_profile_complete()
        return jsonify({
            'message': 'Login successful', 
            'user': user.to_dict(),
            'profile_complete': profile_complete
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    """Get current user information"""
    try:
        id_token = request.json.get('idToken')
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get('email')
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({'user': user.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
    
@auth_bp.route('/all-users', methods=['GET'])
def get_all_users():
    """Get all users"""
    try:
        users = User.query.filter(User.role != UserRole.ADMIN).all()
        return jsonify({'users': [user.to_dict() for user in users]}), 200
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
    
@auth_bp.route('/all-creators', methods=['GET'])
def get_all_creators():
    """Get all creators"""
    try:
        creators = User.query.filter(User.role == UserRole.CREATOR).all()
        return jsonify({'creators': [creator.to_dict() for creator in creators]}), 200
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
    
@auth_bp.route('/all-viewers', methods=['GET'])
def get_all_viewers():
    """Get all viewers"""
    try:
        viewers = User.query.filter(User.role == UserRole.VIEWER).all()
        return jsonify({'viewers': [viewer.to_dict() for viewer in viewers]}), 200
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500