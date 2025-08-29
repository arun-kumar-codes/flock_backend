from datetime import datetime
from flask import Blueprint, request, current_app
import stripe

from app import db
from app.models import StripeAccount, WithdrawalRequest

stripe_webhooks_bp = Blueprint('stripe_webhooks', __name__)

@stripe_webhooks_bp.route('/webhook/account', methods=['POST'])
def stripe_webhook_account():
    """Handle Stripe webhooks"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    print("Webhook received")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, current_app.config['STRIPE_WEBHOOK_ACCOUNT_SECRET']
        )
    except ValueError as e:
        print(f"Invalid payload: {e}")
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        print(f"Invalid signature: {e}")
        return 'Invalid signature', 400
    
    if event['type'] == 'account.updated':
        handle_account_updated(event['data']['object'])
    elif event['type'] == 'transfer.created':
        handle_transfer_created(event['data']['object'])
    elif event['type'] == 'transfer.failed':
        handle_transfer_failed(event['data']['object'])
    elif event['type'] == 'account.application.deauthorized':
        handle_account_deauthorized(event['account'])
    
    return 'OK', 200

def handle_account_updated(account):
    """Handle Stripe account updates (onboarding completion, status changes)"""
    try:
        print(f"Account updated: {account.id}")
        stripe_account = StripeAccount.query.filter_by(
            stripe_account_id=account.id
        ).first()
        
        if stripe_account:
            stripe_account.charges_enabled = account.charges_enabled
            stripe_account.payouts_enabled = account.payouts_enabled
            stripe_account.account_status = 'active' if account.charges_enabled and account.payouts_enabled else 'pending'
            
            db.session.commit()
            
    except Exception as e:
        db.session.rollback()

def handle_transfer_created(transfer):
    """Handle successful transfer creation (withdrawal processed)"""
    try:
        print(f"Transfer created: {transfer.id}")
        
        # Find our withdrawal request using transfer metadata
        withdrawal = WithdrawalRequest.query.filter_by(
            stripe_transfer_id=transfer.id
        ).first()
        
        if withdrawal:
            withdrawal.status = 'completed'
            withdrawal.processed_at = datetime.utcnow()
            db.session.commit()
            
    except Exception as e:
        db.session.rollback()

def handle_transfer_failed(transfer):
    """Handle failed transfers (withdrawal failed)"""
    try:
        print(f"Transfer failed: {transfer.id}")
        
        withdrawal = WithdrawalRequest.query.filter_by(
            stripe_transfer_id=transfer.id
        ).first()
        
        if withdrawal:
            withdrawal.status = 'failed'
            withdrawal.failure_reason = transfer.failure_reason
            db.session.commit()
            
            
    except Exception as e:
        db.session.rollback()

def handle_account_deauthorized(account):
    """Handle when a creator deauthorizes their Stripe account"""
    try:
        print(f"Account deauthorized: {account}")
        
        stripe_account = StripeAccount.query.filter_by(
            stripe_account_id=account
        ).first()
        
        if stripe_account:
            db.session.delete(stripe_account)
            db.session.commit()
            
    except Exception as e:
        db.session.rollback()
        
@stripe_webhooks_bp.route('/webhook/connect', methods=['POST'])
def stripe_webhook_connect():
    """Handle Stripe webhooks"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    print("Webhook received")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, current_app.config['STRIPE_WEBHOOK_CONNECT_SECRET']
        )
    except ValueError as e:
        print(f"Invalid payload: {e}")
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        print(f"Invalid signature: {e}")
        return 'Invalid signature', 400
    
    if event['type'] == 'account.updated':
        handle_account_updated(event['data']['object'])
    elif event['type'] == 'transfer.created':
        handle_transfer_created(event['data']['object'])
    elif event['type'] == 'transfer.failed':
        handle_transfer_failed(event['data']['object'])
    elif event['type'] == 'account.application.deauthorized':
        handle_account_deauthorized(event['account'])
    
    return 'OK', 200

def handle_account_updated(account):
    """Handle Stripe account updates (onboarding completion, status changes)"""
    try:
        print(f"Account updated: {account.id}")
        
        stripe_account = StripeAccount.query.filter_by(
            stripe_account_id=account.id
        ).first()
        
        if stripe_account:
            stripe_account.charges_enabled = account.charges_enabled
            stripe_account.payouts_enabled = account.payouts_enabled
            stripe_account.account_status = 'active' if account.charges_enabled and account.payouts_enabled else 'pending'
            
            db.session.commit()
            
    except Exception as e:
        db.session.rollback()

def handle_transfer_created(transfer):
    """Handle successful transfer creation (withdrawal processed)"""
    try:
        print(f"Transfer created: {transfer.id}")
        
        withdrawal = WithdrawalRequest.query.filter_by(
            stripe_transfer_id=transfer.id
        ).first()
        
        if withdrawal:
            withdrawal.status = 'completed'
            withdrawal.processed_at = datetime.utcnow()
            db.session.commit()
            
            
    except Exception as e:
        db.session.rollback()

def handle_transfer_failed(transfer):
    """Handle failed transfers (withdrawal failed)"""
    try:
        print(f"Transfer failed: {transfer.id}")
        
        withdrawal = WithdrawalRequest.query.filter_by(
            stripe_transfer_id=transfer.id
        ).first()
        
        if withdrawal:
            withdrawal.status = 'failed'
            withdrawal.failure_reason = transfer.failure_reason
            db.session.commit()
            
    except Exception as e:
        db.session.rollback()

def handle_account_deauthorized(account):
    """Handle when a creator deauthorizes their Stripe account"""
    try:
        print(f"Account deauthorized: {account}")
        
        stripe_account = StripeAccount.query.filter_by(
            stripe_account_id=account
        ).first()
        
        if stripe_account:
            db.session.delete(stripe_account)
            db.session.commit()
    except Exception as e:
        db.session.rollback()