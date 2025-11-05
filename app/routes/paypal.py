from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, PayPalAccount, WithdrawalRequest
from app.services.paypal_service import PayPalService
from app.utils import creator_required

paypal_bp = Blueprint('paypal', __name__)

@paypal_bp.route("/setup-paypal-account", methods=["POST"])
@jwt_required()
@creator_required
def setup_paypal_account():
    """Unified setup for PayPal Connect — mirrors Stripe's onboarding logic"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    if not creator:
        return jsonify({"error": "Creator not found"}), 404

    paypal_service = PayPalService()

    try:
        existing_account = PayPalAccount.query.filter_by(creator_id=creator.id).first()

        # === CASE 1: Already verified ===
        if existing_account and existing_account.account_status == "verified":
            return jsonify({
                "error": "PayPal account already connected",
                "status": "already_active"
            }), 400

        # === CASE 2: Pending — regenerate connect link ===
        if existing_account and existing_account.account_status == "pending":
            auth_url = paypal_service.get_authorize_url()
            return jsonify({
                "success": True,
                "status": "existing_incomplete",
                "onboarding_url": auth_url,
                "message": "Continue PayPal verification process"
            }), 200

        # === CASE 3: New account — create and send onboarding link ===
        auth_url = paypal_service.get_authorize_url()

        # Create a placeholder PayPal account (pending)
        new_account = PayPalAccount(
            creator_id=creator.id,
            paypal_email=None,
            account_status="pending"
        )
        db.session.add(new_account)
        db.session.commit()

        return jsonify({
            "success": True,
            "status": "new_created",
            "onboarding_url": auth_url,
            "message": "New PayPal onboarding started"
        }), 200

    except Exception as e:
        db.session.rollback()
        print("PayPal setup error:", e)
        return jsonify({"error": str(e)}), 500


# === OAuth callback (handles user redirect back from PayPal) ===
@paypal_bp.route("/paypal/callback", methods=["GET"])
def paypal_callback():
    """Handle PayPal OAuth redirect"""
    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        return jsonify({"error": "Missing authorization code"}), 400

    paypal_service = PayPalService()
    try:
        token_data = paypal_service.get_access_token_from_code(code)
        access_token = token_data.get("access_token")

        user_info = paypal_service.get_user_info(access_token)
        verified_email = user_info.get("email")

        if not verified_email:
            return jsonify({"error": "Unable to verify PayPal account"}), 400

        # Update the most recent pending PayPal account
        account = PayPalAccount.query.order_by(PayPalAccount.id.desc()).first()
        if not account:
            return jsonify({"error": "No pending PayPal account found"}), 404

        account.paypal_email = verified_email
        account.account_status = "verified"
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "PayPal account connected successfully",
            "account": account.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        print("PayPal callback error:", e)
        return jsonify({"error": str(e)}), 500
    

@paypal_bp.route('/paypal-account', methods=['GET'])
@jwt_required()
@creator_required
def get_paypal_account():
    """Get PayPal account info"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    account = PayPalAccount.query.filter_by(creator_id=creator.id).first()
    if not account:
        return jsonify({"error": "No PayPal account found"}), 404
    return jsonify({"success": True, "account": account.to_dict()}), 200


@paypal_bp.route('/request-paypal-withdrawal', methods=['POST'])
@jwt_required()
@creator_required
def request_paypal_withdrawal():
    """Process PayPal payout"""
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()
    data = request.get_json()
    amount = float(data.get("amount", 0))

    if amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    account = PayPalAccount.query.filter_by(creator_id=creator.id).first()
    if not account:
        return jsonify({"error": "No PayPal account linked"}), 400

    try:
        # ✅ Step 1: Send PayPal payout
        paypal_service = PayPalService()
        payout = paypal_service.send_payout(account.paypal_email, amount)
        batch_id = payout.get("batch_header", {}).get("payout_batch_id")

        # ✅ Step 2: Record withdrawal request in unified model
        withdrawal = WithdrawalRequest(
            creator_id=creator.id,
            amount=amount,
            payout_method="paypal",
            transaction_id=batch_id,
            account_email=account.paypal_email,
            status="processing"
        )
        db.session.add(withdrawal)
        db.session.commit()

        return jsonify({
            "success": True,
            "withdrawal": withdrawal.to_dict(),
            "payout_response": payout
        }), 200

    except Exception as e:
        db.session.rollback()
        print("PayPal withdrawal error:", e)
        return jsonify({"error": str(e)}), 500


@paypal_bp.route('/remove-paypal', methods=['POST'])
@jwt_required()
@creator_required
def remove_paypal_account():
    email = get_jwt_identity()
    creator = User.query.filter_by(email=email).first()

    account = PayPalAccount.query.filter_by(creator_id=creator.id).first()
    if not account:
        return jsonify({"error": "No PayPal account found"}), 404

    try:
        db.session.delete(account)
        db.session.commit()
        return jsonify({"success": True, "message": "PayPal account removed successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
