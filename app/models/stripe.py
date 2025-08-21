from datetime import datetime
from sqlalchemy import Numeric, Text
from app import db

class StripeAccount(db.Model):
    """Stripe Connect accounts for creators"""
    __tablename__ = 'stripe_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    stripe_account_id = db.Column(db.String(255), nullable=False, unique=True)
    account_status = db.Column(db.String(50), default='pending')  # pending, active, restricted
    charges_enabled = db.Column(db.Boolean, default=False)
    payouts_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    creator = db.relationship('User', backref=db.backref('stripe_account', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'creator_id': self.creator_id,
            'stripe_account_id': self.stripe_account_id,
            'account_status': self.account_status,
            'charges_enabled': self.charges_enabled,
            'payouts_enabled': self.payouts_enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class WithdrawalRequest(db.Model):
    """Withdrawal requests from creators"""
    __tablename__ = 'withdrawal_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    stripe_transfer_id = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default='pending')  # pending, processing, completed, failed
    failure_reason = db.Column(Text, nullable=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    creator = db.relationship('User', backref=db.backref('withdrawal_requests', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'creator_id': self.creator_id,
            'amount': float(self.amount),
            'stripe_transfer_id': self.stripe_transfer_id,
            'status': self.status,
            'failure_reason': self.failure_reason,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None
        }