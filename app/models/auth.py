import bcrypt
from enum import Enum
from datetime import datetime
from sqlalchemy import Table, Column, Integer, ForeignKey, DateTime
from app import db

class UserRole(Enum):
    CREATOR = "Creator"
    VIEWER = "Viewer"
    ADMIN = "Admin"
    
followers = Table('followers',
    db.metadata,
    Column('follower_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('followed_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('created_at', DateTime, default=datetime.utcnow)
)

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    profile_picture = db.Column(db.String(500), nullable=True)
    role = db.Column(db.Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    following = db.relationship(
        'User', 
        secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'),
        lazy='dynamic'
    )
    
    def __init__(self, username=None, email=None, password=None, role=UserRole.VIEWER):
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
        return self.username is not None and self.password_hash is not None
    
    def complete_profile(self, username, password):
        """Complete user profile with username and password (initial profile setup)"""
        self.username = username
        self.password_hash = self._hash_password(password)
    
    def update_profile(self, username=None, profile_picture=None):
        """Update user profile information (username and profile picture)"""
        if username is not None:
            self.username = username
        if profile_picture is not None:
            self.profile_picture = profile_picture
            
    def follow(self, user):
        """Follow another user"""
        if not self.is_following(user):
            self.following.append(user)
            return True
        return False
    
    def unfollow(self, user):
        """Unfollow another user"""
        if self.is_following(user):
            self.following.remove(user)
            return True
        return False
    
    def is_following(self, user):
        """Check if this user is following another user"""
        return self.following.filter(followers.c.followed_id == user.id).count() > 0
    
    def get_followers_count(self):
        """Get number of followers"""
        return self.followers.count()
    
    def get_following_count(self):
        """Get number of users being followed"""
        return self.following.count()
    
    def get_followers(self, limit=None):
        """Get list of followers"""
        query = self.followers
        if limit:
            query = query.limit(limit)
        return query.all()
    
    def get_following(self, limit=None):
        """Get list of users being followed"""
        query = self.following
        if limit:
            query = query.limit(limit)
        return query.all()
    
    def get_total_earnings(self):
        """Get total earnings for the creator"""
        if self.role != UserRole.CREATOR:
            return 0.0
        from app.models import CreatorEarnings
        total = db.session.query(db.func.sum(CreatorEarnings.earnings))\
            .filter(CreatorEarnings.creator_id == self.id)\
            .scalar()
        return float(total) if total else 0.0
    
    def get_monthly_earnings(self, year=None, month=None):
        """Get earnings for a specific month"""
        if self.role != UserRole.CREATOR:
            return 0.0
        
        if year is None:
            year = datetime.utcnow().year
        if month is None:
            month = datetime.utcnow().month
        from app.models import CreatorEarnings
        total = db.session.query(db.func.sum(CreatorEarnings.earnings))\
            .filter(CreatorEarnings.creator_id == self.id)\
            .filter(db.func.extract('year', CreatorEarnings.calculated_at) == year)\
            .filter(db.func.extract('month', CreatorEarnings.calculated_at) == month)\
            .scalar()
        return float(total) if total else 0.0
    
    def get_earnings_history(self, limit=None):
        """Get earnings history for the creator"""
        if self.role != UserRole.CREATOR:
            return []
        from app.models import CreatorEarnings
        query = CreatorEarnings.query.filter_by(creator_id=self.id)\
            .order_by(CreatorEarnings.calculated_at.desc())
        
        if limit:
            query = query.limit(limit)
        
        return [earning.to_dict() for earning in query.all()]
    
    def to_dict(self):
        """Convert user to dictionary (excluding password)"""
        base_dict = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'profile_picture': self.profile_picture,
            'role': self.role.value,
            'followers_count': self.get_followers_count(),
            'following_count': self.get_following_count()
        }
        
        # Add earnings info for creators
        if self.role == UserRole.CREATOR:
            base_dict.update({
                'total_earnings': self.get_total_earnings(),
                'monthly_earnings': self.get_monthly_earnings()
            })
        
        return base_dict
    
    def __repr__(self):
        return f'<User {self.username}>' 
    
class Invitation(db.Model):
    __tablename__ = 'invitations'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    invited_on = db.Column(db.DateTime, default=datetime.utcnow)
    