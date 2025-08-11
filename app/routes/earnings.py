from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity


from app.models import User, CreatorEarnings, CPMConfig
from app.utils import creator_required

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