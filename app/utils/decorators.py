from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity

from app.models import User, UserRole


def admin_required(fn):
    """
    Decorator to require admin role for accessing protected endpoints.
    This decorator should be used after @jwt_required() decorator.
    
    Usage:
        @app.route('/admin-only')
        @jwt_required()
        @admin_required
        def admin_only_endpoint():
            return jsonify({'message': 'Admin access granted'})
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            email = get_jwt_identity()
            user = User.query.filter_by(email=email).first()
            
            if not user:
                return jsonify({'error': 'User not found'}), 404

            if user.role != UserRole.ADMIN:
                return jsonify({'error': 'Admin access required'}), 403

            return fn(*args, **kwargs)
            
        except Exception as e:
            return jsonify({'error': 'Internal server error'}), 500
    
    return wrapper


def creator_required(fn):
    """
    Decorator to require creator role for accessing protected endpoints.
    This decorator should be used after @jwt_required() decorator.
    
    Usage:
        @app.route('/creator-only')
        @jwt_required()
        @creator_required
        def creator_only_endpoint():
            return jsonify({'message': 'Creator access granted'})
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            email = get_jwt_identity()
            user = User.query.filter_by(email=email).first()
            
            if not user:
                return jsonify({'error': 'User not found'}), 404

            if user.role != UserRole.CREATOR:
                return jsonify({'error': 'Creator access required'}), 403

            return fn(*args, **kwargs)
            
        except Exception as e:
            return jsonify({'error': 'Internal server error'}), 500
    
    return wrapper