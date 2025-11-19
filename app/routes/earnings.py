from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import User, CreatorEarnings, CPMConfig, StripeAccount, WithdrawalRequest
from app.services import StripeService
from app.utils import creator_required
from app.utils.email import send_withdrawal_request_email

earnings_bp = Blueprint('earnings', __name__)


@earnings_bp.route('/get-earnings', methods=['GET'])
@jwt_required()
@creator_required
def get_earnings():
    """Get creator's earnings overview"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    
    if not creator:
        return jsonify({'error': 'Creator not found'}), 404
    
    return jsonify({
        'success': True,
        'earnings': {
            'total_earnings': creator.get_total_earnings(),
            'current_month_earnings': creator.get_monthly_earnings(),
            'earnings_history': creator.get_earnings_history(limit=5)
        }
    })
    
    
@earnings_bp.route('/get-earnings-history', methods=['GET'])
@jwt_required()
@creator_required
def get_earnings_history():
    """Get detailed earnings history"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    
    if not creator:
        return jsonify({'error': 'Creator not found'}), 404
    
    earnings = CreatorEarnings.query.filter_by(creator_id=creator.id)\
        .order_by(CreatorEarnings.calculated_at.desc())
    
    return jsonify({
        'success': True,
        'earnings': {
            'items': [earning.to_dict() for earning in earnings],
            'total': earnings.count()
        }
    })
    
@earnings_bp.route('/active-cpm-rate', methods=['GET'])
@jwt_required()
@creator_required
def get_current_cpm():
    """Get current CPM rate"""
    config = CPMConfig.get_active_config()
    
    return jsonify({
        'success': True,
        'cpm_rate': float(config.cpm_rate) if config else 2.00,
        'description': f'${float(config.cpm_rate) if config else 2.00} per 1,000 minutes viewed'
    })
    
    
@earnings_bp.route('/setup-stripe-account', methods=['POST'])
@jwt_required()
@creator_required
def setup_stripe_account():
    """Setup Stripe Connect account for creator"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    
    if not creator:
        return jsonify({'error': 'Creator not found'}), 404
    
    try:
        existing_account = StripeAccount.query.filter_by(creator_id=creator.id).first()
        
        if existing_account:
            if existing_account.account_status == 'pending':
                stripe_service = StripeService()
                
                try:
                    account_link = stripe_service.get_account_link(
                        stripe_account_id=existing_account.stripe_account_id,
                        refresh_url="https://beta.flocktogether.xyz/dashboard/payout",
                        return_url="https://beta.flocktogether.xyz/dashboard/payout"
                    )
                    
                    return jsonify({
                        'success': True,
                        'account_id': existing_account.stripe_account_id,
                        'onboarding_url': account_link.url,
                        'message': 'Account exists, continuing onboarding...',
                        'status': 'existing_incomplete'
                    })
                    
                except Exception as e:
                    stripe_service.delete_account(existing_account.stripe_account_id)
                    db.session.delete(existing_account)
                    db.session.commit()
                    
            elif existing_account.account_status == 'active':
                return jsonify({
                    'error': 'Stripe account already active',
                    'status': 'already_active'
                }), 400
        
        stripe_service = StripeService()
        account = stripe_service.create_connect_account(
            creator_id=creator.id,
            email=creator.email
        )
        
        account_link = stripe_service.get_account_link(
            stripe_account_id=account.id,
            refresh_url="https://beta.flocktogether.xyz/dashboard/payout",
            return_url="https://beta.flocktogether.xyz/dashboard/payout"
        )
        
        return jsonify({
            'success': True,
            'account_id': account.id,
            'onboarding_url': account_link.url,
            'message': 'New account created',
            'status': 'new_created'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@earnings_bp.route('/stripe-account', methods=['GET'])
@jwt_required()
@creator_required
def get_stripe_account():
    """Get creator's Stripe account details"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    
    stripe_account = StripeAccount.query.filter_by(creator_id=creator.id).first()
    if not stripe_account:
        return jsonify({'success': False, 'error': 'No Stripe account found'}), 400
    
    return jsonify({
        'success': True,
        'account': stripe_account.to_dict()
    })

@earnings_bp.route('/stripe-account-status', methods=['GET'])
@jwt_required()
@creator_required
def get_stripe_account_status():
    """Get creator's Stripe account status"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    
    stripe_account = StripeAccount.query.filter_by(creator_id=creator.id).first()
    if not stripe_account:
        return jsonify({'error': 'No Stripe account found'}), 400
    
    try:
        stripe_service = StripeService()
        status = stripe_service.get_account_status(stripe_account.stripe_account_id)
        
        stripe_account.charges_enabled = status['charges_enabled']
        stripe_account.payouts_enabled = status['payouts_enabled']
        stripe_account.account_status = 'active' if status['charges_enabled'] and status['payouts_enabled']   else 'pending'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'account': stripe_account.to_dict(),
            'stripe_status': status
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@earnings_bp.route('/remove-stripe-account', methods=['POST'])
@jwt_required()
@creator_required
def remove_stripe_account():
    """Remove Stripe account"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()

    stripe_account = StripeAccount.query.filter_by(creator_id=creator.id).first()
    if not stripe_account:
        return jsonify({'error': 'No Stripe account found'}), 400

    stripe_service = StripeService()
    try:
        # Attempt to delete remotely
        try:
            stripe_service.delete_account(stripe_account.stripe_account_id)
        except Exception as inner_e:
            print(f"⚠️ Stripe deletion failed (already deleted?): {inner_e}")

        # Always remove from DB
        db.session.delete(stripe_account)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Stripe account removed successfully'
        }), 200
    except Exception as e:
        db.session.rollback()
        print("Error removing Stripe account:", e)
        return jsonify({'error': str(e)}), 500
    

@earnings_bp.route('/request-withdrawal', methods=['POST'])
@jwt_required()
@creator_required
def request_withdrawal():
    """Request a withdrawal of earnings"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    
    if not creator:
        return jsonify({'error': 'Creator not found'}), 404
    
    data = request.get_json()
    amount = data.get('amount')
    
    if not amount or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    available_earnings = creator.get_total_earnings()
    if amount > available_earnings:
        return jsonify({'error': 'Insufficient earnings'}), 400
    
    stripe_account = StripeAccount.query.filter_by(creator_id=creator.id).first()
    if not stripe_account:
        return jsonify({'error': 'Please setup Stripe account first'}), 400
    
    if not stripe_account.payouts_enabled:
        return jsonify({'error': 'Stripe account not ready for payouts'}), 400
    
    try:
        stripe_service = StripeService()
        withdrawal = stripe_service.process_withdrawal(creator.id, amount)
        
        send_withdrawal_request_email(
            creator.email,
            creator.username,
            amount,
            "Stripe"
        )
        
        return jsonify({
            'success': True,
            'withdrawal': withdrawal.to_dict()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@earnings_bp.route('/withdrawal-history', methods=['GET'])
@jwt_required()
@creator_required
def get_withdrawal_history():
    """Get creator's withdrawal history"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    
    withdrawals = WithdrawalRequest.query.filter_by(creator_id=creator.id)\
        .order_by(WithdrawalRequest.requested_at.desc())
    
    return jsonify({
        'success': True,
        'withdrawals': [w.to_dict() for w in withdrawals]
    })

@earnings_bp.route('/available-for-withdrawal', methods=['GET'])
@jwt_required()
@creator_required
def get_available_for_withdrawal():
    """Get amount available for withdrawal"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    
    total_earnings = creator.get_total_earnings()
    
    all_withdrawals = db.session.query(db.func.sum(WithdrawalRequest.amount))\
        .filter_by(creator_id=creator.id)\
        .filter(WithdrawalRequest.status.in_(['processing', 'completed']))\
        .scalar()
    
    total_withdrawn = float(all_withdrawals) if all_withdrawals else 0.0
    available_amount = total_earnings - total_withdrawn
    
    pending_withdrawals = db.session.query(db.func.sum(WithdrawalRequest.amount))\
        .filter_by(creator_id=creator.id, status='processing')\
        .scalar()
    
    completed_withdrawals = db.session.query(db.func.sum(WithdrawalRequest.amount))\
        .filter_by(creator_id=creator.id, status='completed')\
        .scalar()
    
    return jsonify({
        'success': True,
        'total_earnings': total_earnings,
        'total_withdrawn': total_withdrawn,
        'pending_withdrawals': float(pending_withdrawals) if pending_withdrawals else 0.0,
        'completed_withdrawals': float(completed_withdrawals) if completed_withdrawals else 0.0,
        'available_for_withdrawal': max(0, available_amount)
    })