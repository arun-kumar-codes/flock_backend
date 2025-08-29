from datetime import datetime
from decimal import Decimal
from enum import Enum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList

from app import db
from app.models import User

class VideoStatus(Enum):
    DRAFT = 'draft'
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
    is_draft = db.Column(db.Boolean, default=False, index=True)
    status = db.Column(db.Enum(VideoStatus), default=VideoStatus.PUBLISHED, index=True)
    reason_for_rejection = db.Column(db.String(1000), nullable=True)
    archived = db.Column(db.Boolean, default=False, index=True)
    likes = db.Column(db.Integer, default=0, index=True)
    views = db.Column(db.Integer, default=0, index=True)
    total_watch_time = db.Column(db.Integer, default=0)
    liked_by = db.Column(MutableList.as_mutable(ARRAY(db.Integer)), default=list)
    viewed_by = db.Column(MutableList.as_mutable(ARRAY(db.Integer)), default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    creator = db.relationship('User', backref=db.backref('videos', lazy=True)) 
    comments = db.relationship('VideoComment', backref='video', lazy=True, cascade='all, delete-orphan')
    watch_times = db.relationship('VideoWatchTime', backref='video', lazy=True, cascade='all, delete-orphan')
    
    def __init__(self, title, video, created_by, description=None, thumbnail=None, 
                 duration=None, format=None, is_draft=False):
        self.title = title
        self.video = video
        self.created_by = created_by
        self.description = description
        self.thumbnail = thumbnail
        self.duration = duration
        self.format = format
        self.is_draft = is_draft
        self.status = VideoStatus.DRAFT if is_draft else VideoStatus.PUBLISHED
        self.archived = False
        self.likes = 0
        self.views = 0
        self.total_watch_time = 0
        self.liked_by = []
        self.viewed_by = []
    
    def publish(self):
        """Publish the video"""
        self.status = VideoStatus.PUBLISHED
        self.is_draft = False
        return True
    
    def reject(self, reason):
        """Reject video by admin"""
        if self.status == VideoStatus.PUBLISHED:
            self.status = VideoStatus.REJECTED
            self.reason_for_rejection = reason
            return True
        return False
    
    def delete(self):
        """Delete the video"""
        try:
            db.session.delete(self)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
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
    
    def calculate_earnings_for_watch_time(self, watch_time_seconds):
        """Calculate earnings for watch time and create earnings entry"""
        
        watch_time_minutes = watch_time_seconds / 60.0
        
        from app.models import CreatorEarnings, CPMConfig
        cpm_config = CPMConfig.get_active_config()
        if not cpm_config:
            cpm_rate = Decimal('2.00')
        else:
            cpm_rate = cpm_config.cpm_rate
        
        earnings = (Decimal(str(watch_time_minutes)) / Decimal('1000')) * cpm_rate
        
        earnings_entry = CreatorEarnings(
            creator_id=self.created_by,
            video_id=self.id,
            watch_time_minutes=int(watch_time_minutes),
            earnings=earnings,
            cpm_rate_used=cpm_rate
        )
        
        db.session.add(earnings_entry)
        return earnings_entry

    def add_watch_time(self, user_id, watch_time_seconds):
        """Add watch time from a user"""
        watch_time_entry = VideoWatchTime.query.filter_by(
            video_id=self.id, 
            user_id=user_id
        ).first()
        
        if not watch_time_entry:
            watch_time_entry = VideoWatchTime(
                video_id=self.id,
                user_id=user_id,
                watch_time=watch_time_seconds
            )
            db.session.add(watch_time_entry)
            self.calculate_earnings_for_watch_time(watch_time_seconds)
            self.total_watch_time += watch_time_seconds
            
    def get_total_earnings(self):
        """Get total earnings for this video"""
        from app.models import CreatorEarnings
        total = db.session.query(db.func.sum(CreatorEarnings.earnings))\
            .filter(CreatorEarnings.video_id == self.id)\
            .scalar()
        return float(total) if total else 0.0
    
    def get_user_watch_time(self, user_id):
        """Get watch time for a specific user"""
        watch_time_entry = VideoWatchTime.query.filter_by(
            video_id=self.id, 
            user_id=user_id
        ).first()
        return watch_time_entry.watch_time if watch_time_entry else 0
    
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
    
    def format_watch_time(self, seconds):
        """Format watch time in HH:MM:SS format"""
        if not seconds:
            return "00:00"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds_remainder = seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds_remainder:02d}"
        else:
            return f"{minutes:02d}:{seconds_remainder:02d}"
        
    def is_following_creator(self, user_id):
        """Check if a user is following the video creator"""
        if not user_id or not self.creator:
            return False
        requesting_user = User.query.get(user_id)
        if not requesting_user:
            return False
        return requesting_user.is_following(self.creator)
    
    def to_dict(self, user_id=None):
        """Convert video to dictionary"""
        video_id = self.video.strip().split("/")[-2] if self.video else None

        return {
            'id': self.id,
            'video_id': video_id,
            'title': self.title,
            'description': self.description,
            'video': self.video,
            'thumbnail': self.thumbnail,
            'duration': self.duration,
            'duration_formatted': self.format_duration(),
            'format': self.format,
            'is_draft': self.is_draft,
            'reason_for_rejection': self.reason_for_rejection,
            'status': self.status.value if self.status else None,
            'archived': self.archived,
            'likes': self.likes,
            'views': self.views,
            'total_watch_time': self.total_watch_time,
            'total_watch_time_formatted': self.format_watch_time(self.total_watch_time),
            'user_watch_time': self.get_user_watch_time(user_id) if user_id else 0,
            'user_watch_time_formatted': self.format_watch_time(self.get_user_watch_time(user_id)) if user_id else "00:00",
            'liked_by': self.liked_by,
            'viewed_by': self.viewed_by,
            'is_liked': self.is_liked_by(user_id) if user_id else False,
            'is_viewed': self.is_viewed_by(user_id) if user_id else False,
            'is_following': self.is_following_creator(user_id) if user_id else False,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
            'creator': self.creator.to_dict() if self.creator else None,
            'comments_count': len(self.comments),
            'comments': [comment.to_dict() for comment in self.comments]
        }
    
    def __repr__(self):
        return f'<Video {self.title}>'


class VideoWatchTime(db.Model):
    __tablename__ = 'video_watch_times'
    
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('videos.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    watch_time = db.Column(db.Integer, default=0)
    last_watched = db.Column(db.DateTime, default=datetime.utcnow)
    
    viewer = db.relationship('User', backref=db.backref('video_watch_times', lazy=True))
    
    def __init__(self, video_id, user_id, watch_time=0):
        self.video_id = video_id
        self.user_id = user_id
        self.watch_time = watch_time
        self.last_watched = datetime.utcnow()
    
    def to_dict(self):
        """Convert watch time entry to dictionary"""
        return {
            'id': self.id,
            'video_id': self.video_id,
            'user_id': self.user_id,
            'watch_time': self.watch_time,
            'watch_time_formatted': self.video.format_watch_time(self.watch_time) if self.video else "00:00",
            'last_watched': self.last_watched.isoformat() if self.last_watched else None,
            'viewer': self.viewer.to_dict() if self.viewer else None
        }
    
    def __repr__(self):
        return f'<VideoWatchTime {self.id}>'


class VideoComment(db.Model):
    __tablename__ = 'video_comments'
    
    id = db.Column(db.Integer, primary_key=True)
    comment = db.Column(db.Text, nullable=False)
    commented_at = db.Column(db.DateTime, default=datetime.utcnow)
    commented_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('videos.id'), nullable=False)
    
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
