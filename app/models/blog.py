from datetime import datetime
from enum import Enum
from sqlalchemy.dialects.postgresql import ARRAY

from app import db


class BlogStatus(Enum):
    DRAFT = 'draft'
    PENDING_APPROVAL = 'pending_approval'
    PUBLISHED = 'published'
    REJECTED = 'rejected'


class Blog(db.Model):
    __tablename__ = 'blogs'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(500), nullable=True)
    status = db.Column(db.Enum(BlogStatus), default=BlogStatus.DRAFT)
    archived = db.Column(db.Boolean, default=False)
    likes = db.Column(db.Integer, default=0)
    liked_by = db.Column(ARRAY(db.Integer), default=[])
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationship with User (author)
    author = db.relationship('User', backref=db.backref('blogs', lazy=True))
    
    # Relationship with Comment (one-to-many)
    comments = db.relationship('Comment', backref='blog', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, title, content, created_by, image=None):
        self.title = title
        self.content = content
        self.created_by = created_by
        self.image = image
        self.status = BlogStatus.DRAFT
        self.archived = False
        self.likes = 0
        self.liked_by = []
    
    def send_for_approval(self):
        """Send blog for admin approval"""
        if self.status == BlogStatus.DRAFT:
            self.status = BlogStatus.PENDING_APPROVAL
            return True
        return False
    
    def approve(self):
        """Approve blog by admin"""
        if self.status == BlogStatus.PENDING_APPROVAL:
            self.status = BlogStatus.PUBLISHED
            return True
        return False
    
    def reject(self):
        """Reject blog by admin"""
        if self.status == BlogStatus.PENDING_APPROVAL:
            self.status = BlogStatus.REJECTED
            return True
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
    
    def to_dict(self, user_id=None):
        """Convert blog to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'image': self.image,
            'status': self.status.value if self.status else None,
            'archived': self.archived,
            'likes': self.likes,
            'liked_by': self.liked_by,
            'is_liked': self.is_liked_by(user_id) if user_id else False,
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
    
    # Relationship with User (commenter)
    commenter = db.relationship('User', backref=db.backref('comments', lazy=True))
    
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
