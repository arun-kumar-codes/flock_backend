from datetime import datetime
from sqlalchemy import Numeric, Text

from app import db

class StripeAccount(db.Model):
    """Stripe Connect accounts for creators"""
    __tablename__ = 'stripe_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, unique=True)
    stripe_account_id = db.Column(db.String(255), nullable=False, unique=True)
    account_status = db.Column(db.String(50), default='pending')
    charges_enabled = db.Column(db.Boolean, default=False)
    payouts_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    creator = db.relationship('User', backref=db.backref('stripe_account', lazy=True, cascade="all, delete-orphan", passive_deletes=True))
    
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
    """Unified withdrawal requests for all payout methods (Stripe, PayPal, Payoneer, etc.)"""
    __tablename__ = 'withdrawal_requests'

    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    
    # New fields ↓
    payout_method = db.Column(db.String(50), default='stripe')  # 'stripe', 'paypal', or 'payoneer'
    transaction_id = db.Column(db.String(255), nullable=True)   # PayPal batch ID or Stripe transfer ID
    account_email = db.Column(db.String(255), nullable=True)    # PayPal or Payoneer email used
    
    status = db.Column(db.String(50), default='pending')        # pending / processing / completed / failed
    failure_reason = db.Column(Text, nullable=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)

    creator = db.relationship('User', backref=db.backref('withdrawal_requests', lazy=True, cascade="all, delete-orphan", passive_deletes=True))

    def to_dict(self):
        return {
            'id': self.id,
            'creator_id': self.creator_id,
            'amount': float(self.amount),
            'payout_method': self.payout_method,
            'transaction_id': self.transaction_id,
            'account_email': self.account_email,
            'status': self.status,
            'failure_reason': self.failure_reason,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None
        }