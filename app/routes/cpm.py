from decimal import Decimal

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity


from app import db
from app.models import User
from app.models import CPMConfig
from app.utils import admin_required

cpm_bp = Blueprint('cpm', __name__)


@cpm_bp.route('/active-config', methods=['GET'])
@jwt_required()
@admin_required
def get_cpm_config():
    """Get current CPM configuration"""
    config = CPMConfig.get_active_config()
    if not config:
        config = CPMConfig(cpm_rate=2.00)
        db.session.add(config)
        db.session.commit()
    
    return jsonify({
        'success': True,
        'config': config.to_dict()
    })


@cpm_bp.route('/update-config', methods=['PUT'])
@jwt_required()
@admin_required
def update_cpm_config():
    """Update CPM configuration"""
    data = request.get_json()
    cpm_rate = data.get('cpm_rate')
    
    if not cpm_rate or not isinstance(cpm_rate, (int, float)) or cpm_rate < 0:
        return jsonify({'error': 'Valid CPM rate is required'}), 400
    
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    current_config = CPMConfig.get_active_config()
    if current_config:
        current_config.is_active = False
        current_config.updated_by = user.id
    
    new_config = CPMConfig(
        cpm_rate=Decimal(str(cpm_rate)),
        updated_by=user.id
    )
    
    db.session.add(new_config)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'CPM configuration updated successfully',
        'config': new_config.to_dict()
    })
    
@cpm_bp.route('/history', methods=['GET'])
@jwt_required()
@admin_required
def get_cpm_config_history():
    """Get all CPM configurations"""
    configs = CPMConfig.query.filter_by(is_active=False).all()
    return jsonify({
        'success': True,
        'configs': [config.to_dict() for config in configs]
    })
    
@cpm_bp.route('/delete-history', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_cpm_config_history():
    """Delete CPM configuration history"""
    CPMConfig.query.filter_by(is_active=False).delete()
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'CPM configuration history deleted successfully'
    })