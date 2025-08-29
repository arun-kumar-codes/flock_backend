from datetime import datetime
from sqlalchemy import Numeric

from app import db

class CPMConfig(db.Model):
    """Configuration for CPM (Cost Per Mille) settings"""
    __tablename__ = 'cpm_config'
    
    id = db.Column(db.Integer, primary_key=True)
    cpm_rate = db.Column(Numeric(10, 4), default=2.00, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    admin = db.relationship('User', backref=db.backref('cpm_updates', lazy=True))
    
    def __init__(self, cpm_rate=2.00, updated_by=None):
        self.cpm_rate = cpm_rate
        self.updated_by = updated_by
    
    def to_dict(self):
        """Convert CPM config to dictionary"""
        return {
            'id': self.id,
            'cpm_rate': float(self.cpm_rate),
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by': self.updated_by,
            'admin': self.admin.to_dict() if self.admin else None
        }
    
    @classmethod
    def get_active_config(cls):
        """Get the currently active CPM configuration"""
        return cls.query.filter_by(is_active=True).first()
    
    def __repr__(self):
        return f'<CPMConfig ${self.cpm_rate} per 1000 minutes>'