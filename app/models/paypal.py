from datetime import datetime
from app import db

class PayPalAccount(db.Model):
    __tablename__ = 'paypal_accounts'

    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, unique=True)
    paypal_email = db.Column(db.String(255), nullable=True)
    account_status = db.Column(db.String(50), default='verified')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('paypal_account', lazy=True, cascade="all, delete-orphan", passive_deletes=True))

    def to_dict(self):
        return {
            'id': self.id,
            'creator_id': self.creator_id,
            'paypal_email': self.paypal_email,
            'account_status': self.account_status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

