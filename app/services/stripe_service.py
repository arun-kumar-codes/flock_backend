from datetime import datetime

from flask import current_app
import stripe

from app import db
from app.models import StripeAccount, WithdrawalRequest

class StripeService:
    def __init__(self):
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    
    def create_connect_account(self, creator_id, email, country='US'):
        """Create a Stripe Connect account for a creator"""
        try:
            account = stripe.Account.create(
                type='express',
                country=country,
                email=email,
                capabilities={
                    'transfers': {'requested': True},
                    'card_payments': {'requested': True},
                },
                business_type='individual'
            )
            
            # Save to database
            stripe_account = StripeAccount(
                creator_id=creator_id,
                stripe_account_id=account.id,
                account_status='pending'
            )
            db.session.add(stripe_account)
            db.session.commit()
            
            return account
            
        except stripe.error.StripeError as e:
            print(f"Error creating Stripe account: {e}")
            db.session.rollback()
            raise e
    
    def get_account_link(self, stripe_account_id, refresh_url, return_url):
        """Generate account link for onboarding"""
        try:
            account_link = stripe.AccountLink.create(
                account=stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type='account_onboarding'
            )
            return account_link
            
        except stripe.error.StripeError as e:
            print(f"Error creating account link: {e}")
            raise e
        
    def delete_account(self, stripe_account_id):
        """Delete a Stripe account (for cleanup)"""
        try:
            stripe.Account.delete(stripe_account_id)
            print(f"Deleted Stripe account: {stripe_account_id}")
        except stripe.error.StripeError as e:
            print(f"Error deleting account: {e}")
            raise e
    
    def process_withdrawal(self, creator_id, amount):
        """Process a withdrawal request"""
        try:
            # Get creator's Stripe account
            stripe_account = StripeAccount.query.filter_by(creator_id=creator_id).first()
            if not stripe_account:
                raise ValueError("Creator doesn't have a Stripe account")
            
            if not stripe_account.payouts_enabled:
                raise ValueError("Creator's Stripe account is not ready for payouts")
            
            # Create withdrawal request
            withdrawal = WithdrawalRequest(
                creator_id=creator_id,
                amount=amount,
                status='processing'
            )
            db.session.add(withdrawal)
            db.session.commit()
            
            # Create transfer to creator's Stripe account
            transfer = stripe.Transfer.create(
                amount=int(amount * 100),  # Convert to cents
                currency='usd',
                destination=stripe_account.stripe_account_id,
                description=f'Withdrawal for creator {creator_id}',
                metadata={
                    'withdrawal_id': withdrawal.id,
                    'creator_id': creator_id
                }
            )
            
            # Update withdrawal with transfer ID
            withdrawal.stripe_transfer_id = transfer.id
            withdrawal.status = 'completed'
            withdrawal.processed_at = datetime.utcnow()
            db.session.commit()
            
            return withdrawal
            
        except stripe.error.StripeError as e:
            print(f"Error processing withdrawal: {e}")
            if 'withdrawal' in locals():
                withdrawal.status = 'failed'
                withdrawal.failure_reason = str(e)
                db.session.commit()
            db.session.rollback()
            raise e
    
    def get_account_status(self, stripe_account_id):
        """Get the status of a Stripe account"""
        try:
            account = stripe.Account.retrieve(stripe_account_id)
            return {
                'charges_enabled': account.charges_enabled,
                'payouts_enabled': account.payouts_enabled,
                'requirements': account.requirements,
                'details_submitted': account.details_submitted
            }
        except stripe.error.StripeError as e:
            print(f"Error retrieving account status: {e}")
            raise e