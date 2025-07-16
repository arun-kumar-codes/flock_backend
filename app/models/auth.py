import bcrypt
from enum import Enum
from datetime import datetime

from app import db


class UserRole(Enum):
    CREATOR = "Creator"
    VIEWER = "Viewer"
    ADMIN = "Admin"

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    login_user_id = db.Column(db.String(80), unique=True, nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    role = db.Column(db.Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    
    def __init__(self, login_user_id, username=None, email=None, password=None, role=UserRole.VIEWER):
        self.login_user_id = login_user_id
        self.username = username
        self.email = email
        self.password_hash = self._hash_password(password) if password else None
        self.role = role
    
    def _hash_password(self, password):
        """Hash password using bcrypt"""
        if not password:
            return None
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        """Check if provided password matches the hash"""
        if not self.password_hash or not password:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def is_profile_complete(self):
        """Check if user has completed their profile (username, email and password)"""
        return self.username is not None and self.email is not None and self.password_hash is not None
    
    def update_profile(self, username, email, password):
        """Update user profile with username and password"""
        self.username = username
        self.email = email
        self.password_hash = self._hash_password(password)
    
    def to_dict(self):
        """Convert user to dictionary (excluding password)"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role.value
        }
    
    def __repr__(self):
        return f'<User {self.username}>' 
    
class Invitation(db.Model):
    __tablename__ = 'invitations'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    invited_on = db.Column(db.DateTime, default=datetime.utcnow)
    