from flask import Blueprint, request, jsonify

from app.utils import send_invitation_email, is_valid_email

email_bp = Blueprint('email', __name__)


@email_bp.route('/send-invitation', methods=['POST'])
def send_invitation():
    """Send an invitation email to a creator"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        if not is_valid_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        success = send_invitation_email(email)
        
        if success:
            return jsonify({
                'message': 'Invitation email sent successfully',
                'email': email
            }), 200
        else:
            return jsonify({'error': 'Failed to send invitation email or invitation already exists'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


