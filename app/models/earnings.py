from datetime import datetime
from sqlalchemy import Numeric

from app import db

class CreatorEarnings(db.Model):
    """Track earnings for creators based on watchtime"""
    __tablename__ = 'creator_earnings'
    
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('videos.id'), nullable=False)
    watch_time_minutes = db.Column(db.Integer, default=0, nullable=False)
    earnings = db.Column(Numeric(10, 4), default=0.00, nullable=False)
    cpm_rate_used = db.Column(Numeric(10, 4), nullable=False)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    creator = db.relationship('User', backref=db.backref('earnings', lazy=True))
    video = db.relationship('Video', backref=db.backref('earnings', lazy=True))
    
    def __init__(self, creator_id, video_id, watch_time_minutes, earnings, cpm_rate_used):
        self.creator_id = creator_id
        self.video_id = video_id
        self.watch_time_minutes = watch_time_minutes
        self.earnings = earnings
        self.cpm_rate_used = cpm_rate_used
    
    def to_dict(self):
        """Convert earnings entry to dictionary"""
        return {
            'id': self.id,
            'creator_id': self.creator_id,
            'video_id': self.video_id,
            'watch_time_minutes': self.watch_time_minutes,
            'earnings': float(self.earnings),
            'cpm_rate_used': float(self.cpm_rate_used),
            'calculated_at': self.calculated_at.isoformat() if self.calculated_at else None,
            'creator': self.creator.to_dict() if self.creator else None,
            'video': self.video.to_dict() if self.video else None
        }
    
    def __repr__(self):
        return f'<CreatorEarnings ${self.earnings} for {self.watch_time_minutes} minutes>'