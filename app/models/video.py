from datetime import datetime
from enum import Enum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
import os
from app import db


class VideoStatus(Enum):
    DRAFT = 'draft'
    PENDING_APPROVAL = 'pending_approval'
    PUBLISHED = 'published'
    REJECTED = 'rejected'


class Video(db.Model):
    __tablename__ = 'videos'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    video = db.Column(db.String(500), nullable=False)
    thumbnail = db.Column(db.String(500), nullable=True)
    duration = db.Column(db.Integer, nullable=True)
    format = db.Column(db.String(50), nullable=True)
    status = db.Column(db.Enum(VideoStatus), default=VideoStatus.DRAFT)
    archived = db.Column(db.Boolean, default=False)
    likes = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
    liked_by = db.Column(MutableList.as_mutable(ARRAY(db.Integer)), default=list)
    viewed_by = db.Column(MutableList.as_mutable(ARRAY(db.Integer)), default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationship with User (creator)
    creator = db.relationship('User', backref=db.backref('videos', lazy=True))
    
    # Relationship with VideoComment (one-to-many)
    comments = db.relationship('VideoComment', backref='video', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, title, video, created_by, description=None, thumbnail=None, 
                 duration=None, format=None):
        self.title = title
        self.video = video
        self.created_by = created_by
        self.description = description
        self.thumbnail = thumbnail
        self.duration = duration
        self.format = format
        self.status = VideoStatus.DRAFT
        self.archived = False
        self.likes = 0
        self.views = 0
        self.liked_by = []
        self.viewed_by = []
    
    def send_for_approval(self):
        """Send video for admin approval"""
        if self.status == VideoStatus.DRAFT:
            self.status = VideoStatus.PENDING_APPROVAL
            return True
        return False
    
    def approve(self):
        """Approve video by admin"""
        if self.status == VideoStatus.PENDING_APPROVAL:
            self.status = VideoStatus.PUBLISHED
            return True
        return False
    
    def reject(self):
        """Reject video by admin"""
        if self.status == VideoStatus.PENDING_APPROVAL:
            self.status = VideoStatus.REJECTED
            return True
        return False
    
    def archive(self):
        """Archive the video"""
        self.archived = True
        return True
    
    def unarchive(self):
        """Unarchive the video"""
        self.archived = False
        return True
    
    def add_like(self, user_id):
        """Add a like from a user"""
        if user_id not in self.liked_by:
            self.liked_by.append(user_id)
            self.likes += 1
    
    def remove_like(self, user_id):
        """Remove a like from a user"""
        if user_id in self.liked_by:
            self.liked_by.remove(user_id)
            self.likes -= 1
    
    def add_view(self, user_id):
        """Add a view from a user"""
        if user_id not in self.viewed_by:
            self.viewed_by.append(user_id)
            self.views += 1
    
    def is_liked_by(self, user_id):
        """Check if video is liked by a specific user"""
        return user_id in self.liked_by
    
    def is_viewed_by(self, user_id):
        """Check if video is viewed by a specific user"""
        return user_id in self.viewed_by
    
    def format_duration(self):
        """Format duration in HH:MM:SS format"""
        if not self.duration:
            return None
        hours = self.duration // 3600
        minutes = (self.duration % 3600) // 60
        seconds = self.duration % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    
    def to_dict(self, user_id=None):
        """Convert video to dictionary"""
        # Base URL for the backend
        base_url = os.getenv('BACKEND_URL')
        
        # Prepend base URL to video and thumbnail paths if they exist
        video_url = f"{base_url}/{self.video}" if self.video else None
        thumbnail_url = f"{base_url}/{self.thumbnail}" if self.thumbnail else None
        
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'video': video_url,
            'thumbnail': thumbnail_url,
            'duration': self.duration,
            'duration_formatted': self.format_duration(),
            'format': self.format,
            'status': self.status.value if self.status else None,
            'archived': self.archived,
            'likes': self.likes,
            'views': self.views,
            'liked_by': self.liked_by,
            'viewed_by': self.viewed_by,
            'is_liked': self.is_liked_by(user_id) if user_id else False,
            'is_viewed': self.is_viewed_by(user_id) if user_id else False,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
            'creator': self.creator.to_dict() if self.creator else None,
            'comments_count': len(self.comments),
            'comments': [comment.to_dict() for comment in self.comments]
        }
    
    def __repr__(self):
        return f'<Video {self.title}>'


class VideoComment(db.Model):
    __tablename__ = 'video_comments'
    
    id = db.Column(db.Integer, primary_key=True)
    comment = db.Column(db.Text, nullable=False)
    commented_at = db.Column(db.DateTime, default=datetime.utcnow)
    commented_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('videos.id'), nullable=False)
    
    # Relationship with User (commenter)
    commenter = db.relationship('User', backref=db.backref('video_comments', lazy=True, cascade='all, delete-orphan'))
    
    def __init__(self, comment, commented_by, video_id):
        self.comment = comment
        self.commented_by = commented_by
        self.video_id = video_id
    
    def to_dict(self):
        """Convert comment to dictionary"""
        return {
            'id': self.id,
            'comment': self.comment,
            'commented_at': self.commented_at.isoformat() if self.commented_at else None,
            'commented_by': self.commented_by,
            'video_id': self.video_id,
            'commenter': self.commenter.to_dict() if self.commenter else None
        }
    
    def __repr__(self):
        return f'<VideoComment {self.id}>'
