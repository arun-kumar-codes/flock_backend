from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import Blog, User
from app.utils import creator_required

blog_bp = Blueprint('blog', __name__)


@blog_bp.route('/create', methods=['POST'])
@jwt_required()
@creator_required
def create_blog():
    """Create a new blog post"""
    try:
        current_login_user_id = get_jwt_identity()
        user = User.query.filter_by(login_user_id=current_login_user_id).first()
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        title = data.get('title')
        content = data.get('content')
        
        if not title or not content:
            return jsonify({'error': 'Title and content are required'}), 400
        
        if len(title) > 200:
            return jsonify({'error': 'Title must be less than 200 characters'}), 400
        
        # Create new blog
        blog = Blog(
            title=title,
            content=content,
            created_by=user.id
        )
        db.session.add(blog)
        db.session.commit()
        
        return jsonify({
            'message': 'Blog created successfully',
            'blog': blog.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>', methods=['GET'])
@jwt_required()
def get_blog(blog_id):
    """Get a specific blog by ID"""
    try:
        print(blog_id)
        blog = Blog.query.get(blog_id)
        
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        return jsonify({
            'blog': blog.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/get-all', methods=['GET'])
@jwt_required()
def get_all_blogs():
    """Get all blogs with optional pagination and filtering"""
    try:
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        author_id = request.args.get('author_id', type=int)
        
        # Build query
        query = Blog.query
        
        # Filter by author if provided
        if author_id:
            query = query.filter_by(created_by=author_id)
        
        # Order by creation date (newest first)
        query = query.order_by(Blog.created_at.desc())
        
        # Paginate results
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        blogs = pagination.items
        
        return jsonify({
            'blogs': [blog.to_dict() for blog in blogs],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/my-blogs', methods=['GET'])
@jwt_required()
def get_my_blogs():
    """Get blogs created by the current user"""
    try:
        current_login_user_id = get_jwt_identity()
        user = User.query.filter_by(login_user_id=current_login_user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get blogs created by current user
        pagination = Blog.query.filter_by(created_by=user.id)\
            .order_by(Blog.created_at.desc())\
            .paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
        
        blogs = pagination.items
        
        return jsonify({
            'blogs': [blog.to_dict() for blog in blogs],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/like', methods=['POST'])
@jwt_required()
def like_blog(blog_id):
    """Like a blog post"""
    try:
        current_login_user_id = get_jwt_identity()
        user = User.query.filter_by(login_user_id=current_login_user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if user already liked the blog
        if blog.is_liked_by(user.id):
            return jsonify({'error': 'Blog already liked by this user'}), 400
        
        # Add like
        blog.add_like(user.id)
        db.session.commit()
        
        return jsonify({
            'message': 'Blog liked successfully',
            'blog': blog.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/unlike', methods=['POST'])
@jwt_required()
def unlike_blog(blog_id):
    """Unlike a blog post"""
    try:
        current_login_user_id = get_jwt_identity()
        user = User.query.filter_by(login_user_id=current_login_user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if user has liked the blog
        if not blog.is_liked_by(user.id):
            return jsonify({'error': 'Blog not liked by this user'}), 400
        
        # Remove like
        blog.remove_like(user.id)
        db.session.commit()
        
        return jsonify({
            'message': 'Blog unliked successfully',
            'blog': blog.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/toggle-like', methods=['POST'])
@jwt_required()
def toggle_like_blog(blog_id):
    """Toggle like/unlike a blog post"""
    try:
        current_login_user_id = get_jwt_identity()
        user = User.query.filter_by(login_user_id=current_login_user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if user has already liked the blog
        if blog.is_liked_by(user.id):
            # Unlike the blog
            blog.remove_like(user.id)
            action = 'unliked'
        else:
            # Like the blog
            blog.add_like(user.id)
            action = 'liked'
        
        db.session.commit()
        
        return jsonify({
            'message': f'Blog {action} successfully',
            'blog': blog.to_dict(),
            'action': action
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500
