import os
import time
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import Blog, User, BlogStatus
from app.utils import creator_required, allowed_file, admin_required

blog_bp = Blueprint('blog', __name__)


@blog_bp.route('/create', methods=['POST'])
@jwt_required()
@creator_required
def create_blog():
    """Create a new blog post"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        title = request.form.get('title')
        content = request.form.get('content')
        image_file = request.files.get('image')
        
        if not title or not content:
            return jsonify({'error': 'Title and content are required'}), 400
        
        if len(title) > 200:
            return jsonify({'error': 'Title must be less than 200 characters'}), 400
        
        # Handle image upload
        image_path = None
        if image_file and image_file.filename != '':
            if not allowed_file(image_file.filename):
                return jsonify({'error': 'Invalid file type. Allowed types: png, jpg, jpeg, gif, webp'}), 400
            
            # Create upload directory if it doesn't exist
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'blogs')
            os.makedirs(upload_folder, exist_ok=True)
            
            # Secure the filename and save the file
            filename = secure_filename(image_file.filename)
            
            timestamp = int(time.time())
            filename = f"{timestamp}_{filename}"
            
            file_path = os.path.join(upload_folder, filename)
            image_file.save(file_path)
            
            # Store the relative path for database
            image_path = f"static/uploads/blogs/{filename}"
        
        # Create new blog with draft status and not archived
        blog = Blog(
            title=title,
            content=content,
            created_by=user.id,
            image=image_path
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


@blog_bp.route('/<int:blog_id>', methods=['PATCH'])
@jwt_required()
@creator_required
def update_blog(blog_id):
    """Update a blog (title, content, image) - only draft or rejected blogs"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if the user is the creator of the blog
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only update your own blogs'}), 403
        
        # Check if blog can be updated (draft or rejected status only)
        if blog.status not in [BlogStatus.DRAFT, BlogStatus.REJECTED]:
            return jsonify({'error': 'Only draft or rejected blogs can be updated'}), 400
        
        # Get form data for updates
        title = request.form.get('title')
        content = request.form.get('content')
        image_file = request.files.get('image')
        
        # Update fields if provided
        if title is not None:
            if len(title) > 200:
                return jsonify({'error': 'Title must be less than 200 characters'}), 400
            blog.title = title
        
        if content is not None:
            blog.content = content
        
        # Handle image update
        if image_file and image_file.filename != '':
            if not allowed_file(image_file.filename):
                return jsonify({'error': 'Invalid file type. Allowed types: png, jpg, jpeg, gif, webp'}), 400
            
            # Create upload directory if it doesn't exist
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'blogs')
            os.makedirs(upload_folder, exist_ok=True)
            
            # Secure the filename and save the file
            filename = secure_filename(image_file.filename)
            timestamp = int(time.time())
            filename = f"{timestamp}_{filename}"
            
            file_path = os.path.join(upload_folder, filename)
            image_file.save(file_path)
            
            # Store the relative path for database
            blog.image = f"static/uploads/blogs/{filename}"
        
        # If blog was rejected and is being updated, change status back to draft
        if blog.status == BlogStatus.REJECTED:
            blog.status = BlogStatus.DRAFT
        
        db.session.commit()
        
        return jsonify({
            'message': 'Blog updated successfully',
            'blog': blog.to_dict(user.id)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/approve', methods=['PATCH'])
@jwt_required()
@admin_required
def approve_blog(blog_id):
    """Approve a blog by admin"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if blog is pending approval
        if blog.status != BlogStatus.PENDING_APPROVAL:
            return jsonify({'error': 'Only blogs pending approval can be approved'}), 400
        
        # Approve the blog
        if blog.approve():
            db.session.commit()
            return jsonify({
                'message': 'Blog approved successfully',
                'blog': blog.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to approve blog'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/reject', methods=['PATCH'])
@jwt_required()
@admin_required
def reject_blog(blog_id):
    """Reject a blog by admin"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if blog is pending approval
        if blog.status != BlogStatus.PENDING_APPROVAL:
            return jsonify({'error': 'Only blogs pending approval can be rejected'}), 400
        
        # Reject the blog
        if blog.reject():
            db.session.commit()
            return jsonify({
                'message': 'Blog rejected successfully',
                'blog': blog.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to reject blog'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/archive', methods=['PATCH'])
@jwt_required()
@creator_required
def archive_blog(blog_id):
    """Archive a blog"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if the user is the creator of the blog
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only archive your own blogs'}), 403
        
        # Check if blog is already archived
        if blog.archived:
            return jsonify({'error': 'Blog is already archived'}), 400
        
        # Archive the blog
        if blog.archive():
            db.session.commit()
            return jsonify({
                'message': 'Blog archived successfully',
                'blog': blog.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to archive blog'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/unarchive', methods=['PATCH'])
@jwt_required()
@creator_required
def unarchive_blog(blog_id):
    """Unarchive a blog"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if the user is the creator of the blog
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only unarchive your own blogs'}), 403
        
        # Check if blog is not archived
        if not blog.archived:
            return jsonify({'error': 'Blog is not archived'}), 400
        
        # Unarchive the blog
        if blog.unarchive():
            db.session.commit()
            return jsonify({
                'message': 'Blog unarchived successfully',
                'blog': blog.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to unarchive blog'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/send-for-approval', methods=['PATCH'])
@jwt_required()
@creator_required
def send_blog_for_approval(blog_id):
    """Send a draft blog for admin approval"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if the user is the creator of the blog
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only send your own blogs for approval'}), 403
        
        # Check if blog can be sent for approval (draft status)
        if blog.status != BlogStatus.DRAFT:
            return jsonify({'error': 'Only draft blogs can be sent for approval'}), 400
        
        # Send for approval
        if blog.send_for_approval():
            db.session.commit()
            return jsonify({
                'message': 'Blog sent for approval successfully',
                'blog': blog.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to send blog for approval'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>', methods=['GET'])
@jwt_required()
def get_blog(blog_id):
    """Get a specific blog by ID"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        blog = Blog.query.get(blog_id)
        
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        return jsonify({
            'blog': blog.to_dict(user.id if user else None)
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/get-all', methods=['GET'])
@jwt_required()
def get_all_blogs():
    """Get all blogs with optional status filtering"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        # Get query parameters
        status_filter = request.args.get('status')
        
        # Build query - exclude archived blogs and draft blogs
        query = Blog.query.filter_by(archived=False).filter(Blog.status != BlogStatus.DRAFT)
        
        # Apply status filter if provided
        if status_filter:
            # Convert string to enum value
            try:
                status_enum = BlogStatus(status_filter)
                query = query.filter_by(status=status_enum)
            except ValueError:
                return jsonify({'error': 'Invalid status value. Valid values: draft, pending_approval, published, rejected'}), 400
        
        blogs = query.all()
        
        return jsonify({
            'blogs': [blog.to_dict(user.id if user else None) for blog in blogs]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/my-blogs', methods=['GET'])
@jwt_required()
def get_my_blogs():
    """Get blogs created by the current user"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blogs = Blog.query.filter_by(created_by=user.id).all()
        
        return jsonify({
            'blogs': [blog.to_dict(user.id) for blog in blogs]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/like', methods=['POST'])
@jwt_required()
def like_blog(blog_id):
    """Like a blog post"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
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
            'blog': blog.to_dict(user.id)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/unlike', methods=['POST'])
@jwt_required()
def unlike_blog(blog_id):
    """Unlike a blog post"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
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
            'blog': blog.to_dict(user.id)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/toggle-like', methods=['POST'])
@jwt_required()
def toggle_like_blog(blog_id):
    """Toggle like/unlike a blog post"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
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
            'blog': blog.to_dict(user.id),
            'action': action
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500
