from datetime import datetime
from enum import Enum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList

from app import db
from app.models import User


class BlogStatus(Enum):
    DRAFT = 'draft'
    PUBLISHED = 'published'
    REJECTED = 'rejected'


class Blog(db.Model):
    __tablename__ = 'blogs'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(500), nullable=True)
    is_draft = db.Column(db.Boolean, default=False, index=True)
    status = db.Column(db.Enum(BlogStatus), default=BlogStatus.PUBLISHED, index=True)
    reason_for_rejection = db.Column(db.String(1000), nullable=True)
    archived = db.Column(db.Boolean, default=False, index=True)
    likes = db.Column(db.Integer, default=0, index=True)
    liked_by = db.Column(MutableList.as_mutable(ARRAY(db.Integer)), default=list)
    views = db.Column(db.Integer, default=0, index=True)
    viewed_by = db.Column(MutableList.as_mutable(ARRAY(db.Integer)), default=list)
    scheduled_at = db.Column(db.DateTime, nullable=True, index=True)
    is_scheduled = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    author = db.relationship('User', backref=db.backref('blogs', lazy=True))
    comments = db.relationship('Comment', backref='blog', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, title, content, created_by, image=None, is_draft=False, is_scheduled=False, scheduled_at=None):
        self.title = title
        self.content = content
        self.created_by = created_by
        self.image = image
        self.is_draft = is_draft
        self.status = BlogStatus.DRAFT if is_draft else BlogStatus.PUBLISHED
        self.archived = False
        self.likes = 0
        self.liked_by = []
        self.views = 0
        self.viewed_by = []
        self.is_scheduled = is_scheduled
        self.scheduled_at = scheduled_at
    
    def publish(self):
        """Publish the blog"""
        self.status = BlogStatus.PUBLISHED
        self.is_draft = False
        self.is_scheduled = False
        self.scheduled_at = None
        return True
    
    def reject(self, reason):
        """Reject blog by admin"""
        if self.status == BlogStatus.PUBLISHED:
            self.status = BlogStatus.REJECTED
            self.reason_for_rejection = reason
            return True
        return False
    
    def delete(self):
        """Delete the blog"""
        try:
            db.session.delete(self)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            return False
    
    def archive(self):
        """Archive the blog"""
        self.archived = True
        return True
    
    def unarchive(self):
        """Unarchive the blog"""
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
    
    def is_liked_by(self, user_id):
        """Check if blog is liked by a specific user"""
        return user_id in self.liked_by
    
    def add_view(self, user_id):
        """Add a view from a user"""
        if user_id not in self.viewed_by:
            self.viewed_by.append(user_id)
            self.views += 1
    
    def is_viewed_by(self, user_id):
        """Check if blog is viewed by a specific user"""
        return user_id in self.viewed_by
    
    def is_following_author(self, user_id):
        """Check if a user is following the blog author"""
        if not user_id or not self.author:
            return False
        requesting_user = User.query.get(user_id)
        if not requesting_user:
            return False
        return requesting_user.is_following(self.author)
    
    def publish_scheduled(self):
        """Publish a scheduled blog when time comes"""
        if self.is_scheduled and self.scheduled_at and datetime.utcnow() >= self.scheduled_at:
            self.status = BlogStatus.PUBLISHED
            self.is_draft = False
            self.is_scheduled = False
            self.scheduled_at = None
            return True
        return False

    def to_dict(self, user_id=None):
        """Convert blog to dictionary"""

        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'image': self.image,
            'is_draft': self.is_draft,
            'reason_for_rejection': self.reason_for_rejection,
            'status': self.status.value if self.status else None,
            'archived': self.archived,
            'likes': self.likes,
            'liked_by': self.liked_by,
            'views': self.views,
            'viewed_by': self.viewed_by,
            'is_liked': self.is_liked_by(user_id) if user_id else False,
            'is_viewed': self.is_viewed_by(user_id) if user_id else False,
            'is_following_author': self.is_following_author(user_id) if user_id else False,
            'is_scheduled': self.is_scheduled,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
            'author': self.author.to_dict() if self.author else None,
            'comments_count': len(self.comments),
            'comments': [comment.to_dict() for comment in self.comments]
        }
    
    def __repr__(self):
        return f'<Blog {self.title}>'


class Comment(db.Model):
    __tablename__ = 'comments'
    
    id = db.Column(db.Integer, primary_key=True)
    comment = db.Column(db.Text, nullable=False)
    commented_at = db.Column(db.DateTime, default=datetime.utcnow)
    commented_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    blog_id = db.Column(db.Integer, db.ForeignKey('blogs.id'), nullable=False)
    
    commenter = db.relationship('User', backref=db.backref('comments', lazy=True, cascade='all, delete-orphan'))
    
    def __init__(self, comment, commented_by, blog_id):
        self.comment = comment
        self.commented_by = commented_by
        self.blog_id = blog_id
    
    def to_dict(self):
        """Convert comment to dictionary"""
        return {
            'id': self.id,
            'comment': self.comment,
            'commented_at': self.commented_at.isoformat() if self.commented_at else None,
            'commented_by': self.commented_by,
            'blog_id': self.blog_id,
            'commenter': self.commenter.to_dict() if self.commenter else None
        }
    
    def __repr__(self):
        return f'<Comment {self.id}>'
