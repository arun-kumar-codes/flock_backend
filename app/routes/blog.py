import os
import json
import requests
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db, cache
from app.models import Blog, User, BlogStatus, Comment, UserRole
from app.utils import creator_required, allowed_file, admin_required, delete_previous_image, delete_blog_cache

blog_bp = Blueprint('blog', __name__)

CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_IMAGE_URL = os.getenv('CLOUDFLARE_IMAGE_URL')

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
        is_draft = request.form.get('is_draft')
        scheduled_at_str = request.form.get('scheduled_at')
        keywords = request.form.get('keywords')
        keywords = json.loads(keywords) if keywords else []
        age_restricted = request.form.get('age_restricted', 'false').lower() == 'true'
        locations = request.form.get("locations")
        locations = json.loads(locations) if locations else []
        brand_tags = request.form.get('brand_tags')
        brand_tags = json.loads(brand_tags) if brand_tags else []
        paid_promotion = request.form.get('paid_promotion', 'false').lower() == 'true'

        
        if not title or not content:
            return jsonify({'error': 'Title and content are required'}), 400
        
        if len(title) > 200:
            return jsonify({'error': 'Title must be less than 200 characters'}), 400
        
        # Parse scheduled_at if provided
        scheduled_at = None
        is_scheduled = False
        
        if scheduled_at_str:
            try:
                scheduled_at = datetime.fromisoformat(scheduled_at_str.replace('Z', '+00:00'))
                scheduled_at = scheduled_at.replace(tzinfo=None)
                if scheduled_at <= datetime.utcnow():
                    return jsonify({'error': 'Scheduled time must be in the future'}), 400
                is_scheduled = True
                is_draft = True
            except ValueError:
                return jsonify({'error': 'Invalid scheduled_at format. Use ISO format (e.g., 2025-01-15T14:30:00Z)'}), 400
        
        
        image_path = None
        if image_file and image_file.filename != '':
            if not allowed_file(image_file.filename):
                return jsonify({'error': 'Invalid file type. Allowed types: png, jpg, jpeg, gif, webp'}), 400
            
            headers = {
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
            }
            files = {
                "file": (image_file.filename, image_file.stream, image_file.content_type)
            }
            response = requests.post(CLOUDFLARE_IMAGE_URL, headers=headers, files=files)
            if response.status_code == 200:
                image_path = response.json()['result']['variants'][0]
            else:
                return jsonify({'error': 'Image upload failed'}), 400

        blog = Blog(
            title=title,
            content=content,
            created_by=user.id,
            image=image_path,
            keywords=keywords,
            is_draft=is_draft == 'true' or is_scheduled,
            scheduled_at=scheduled_at,
            is_scheduled=is_scheduled,
            age_restricted=age_restricted,
            locations=locations,
            brand_tags=brand_tags,
            paid_promotion=paid_promotion,

        )
        db.session.add(blog)
        db.session.commit()
        delete_blog_cache()
        
        message = 'Blog created successfully'
        if is_scheduled:
            message = 'Blog scheduled successfully'
        
        return jsonify({
            'message': message,
            'blog': blog.to_dict()
        }), 201
        
    except Exception as e:
        print(e)
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>', methods=['PATCH'])
@jwt_required()
@creator_required
def update_blog(blog_id):
    """Update a blog (title, content, image) - only draft, published or rejected blogs"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only update your own blogs'}), 403
        
        if blog.status not in [BlogStatus.DRAFT, BlogStatus.PUBLISHED, BlogStatus.REJECTED]:
            return jsonify({'error': 'Check blog status'}), 400
        
        title = request.form.get('title')
        content = request.form.get('content')
        image_file = request.files.get('image')
        keywords = request.form.get('keywords')
        keywords = json.loads(keywords) if keywords else []
        locations = request.form.get('locations')
        age_restricted = request.form.get('age_restricted')
        paid_promotion = request.form.get("paid_promotion")
        brand_tags = request.form.get("brand_tags")
        
        if locations is not None:
            try:
                # If frontend sends JSON string
                if isinstance(locations, str):
                    locations_list = json.loads(locations) if locations else []
                else:
                    locations_list = locations
                
                # Ensure it's a list
                if not isinstance(locations_list, list):
                    locations_list = []
                
                # Store as list (JSON column)
                blog.locations = locations_list
            except Exception as e:
                print(f"Location parsing error: {e}")
                blog.locations = []
         
            
        if age_restricted is not None:
            blog.age_restricted = str(age_restricted).lower() in ["true", "1", "yes"]
        
        if title is not None:
            if len(title) > 200:
                return jsonify({'error': 'Title must be less than 200 characters'}), 400
            blog.title = title
        
        if content is not None:
            blog.content = content
            
        if keywords is not None:
            blog.set_keywords(keywords)
            
        if brand_tags is not None:
            try:
                brand_tags = json.loads(brand_tags)
                if not isinstance(brand_tags, list):
                    brand_tags = [brand_tags]
            except Exception:
                brand_tags = [b.strip() for b in brand_tags.split(',') if b.strip()]
            blog.brand_tags = brand_tags

        if paid_promotion is not None:
            blog.paid_promotion = str(paid_promotion).lower() in ["true", "1", "yes"]
        
        if image_file and image_file.filename != '':
            if not allowed_file(image_file.filename):
                return jsonify({'error': 'Invalid file type. Allowed types: png, jpg, jpeg, gif, webp'}), 400
            
            headers = {
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
               }
            files = {
                "file": (image_file.filename, image_file.stream, image_file.content_type)
                }
            response = requests.post(CLOUDFLARE_IMAGE_URL, headers=headers, files=files)
            if response.status_code == 200:
                image_path = response.json()['result']['variants'][0]
                delete_previous_image(blog.image)
                blog.image = image_path
            else:
                return jsonify({'error': 'Image upload failed'}), 400
        
        db.session.commit()
        delete_blog_cache()
        return jsonify({
            'message': 'Blog updated successfully',
            'blog': blog.to_dict(user.id)
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@blog_bp.route('/<int:blog_id>/publish', methods=['PATCH'])
@jwt_required()
@creator_required
def publish_blog(blog_id):
    """Publish a blog by creator"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        if blog.status != BlogStatus.DRAFT:
            return jsonify({'error': 'Only draft blogs can be published'}), 400
        
        if blog.publish():
            db.session.commit()
            delete_blog_cache()
            return jsonify({
                'message': 'Blog published successfully',
                'blog': blog.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to publish blog'}), 400
        
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
        
        if blog.status != BlogStatus.PUBLISHED:
            return jsonify({'error': 'Only published blogs can be rejected'}), 400
        reason = request.json.get('reason')
        if not reason:
            return jsonify({'error': 'Reason is required'}), 400

        if blog.reject(reason):
            db.session.commit()
            delete_blog_cache()
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
        
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only archive your own blogs'}), 403
        
        if blog.archived:
            return jsonify({'error': 'Blog is already archived'}), 400
        
        if blog.archive():
            db.session.commit()
            delete_blog_cache()
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
        
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only unarchive your own blogs'}), 403
        
        if not blog.archived:
            return jsonify({'error': 'Blog is not archived'}), 400
        
        if blog.unarchive():
            db.session.commit()
            delete_blog_cache()
            return jsonify({
                'message': 'Blog unarchived successfully',
                'blog': blog.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to unarchive blog'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/delete', methods=['DELETE'])
@jwt_required()
@creator_required
def delete_blog(blog_id):
    """Delete a blog"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only delete your own blogs'}), 403
        
        if blog.delete():
            delete_blog_cache()
            return jsonify({
                'message': 'Blog deleted successfully',
                'blog': blog.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to delete blog'}), 400
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>', methods=['GET'])
@jwt_required(optional=True)
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


@blog_bp.route('/<int:blog_id>/view', methods=['POST'])
@jwt_required()
def add_blog_view(blog_id):
    """Add a view to a blog by a user"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        if blog.status != BlogStatus.PUBLISHED:
            return jsonify({'error': 'Only published blogs can be viewed'}), 400
        
        if blog.archived:
            return jsonify({'error': 'Blog not available'}), 404
        
        blog.add_view(user.id)
        db.session.commit()
        delete_blog_cache()
        return jsonify({
            'message': 'View added successfully',
            'views': blog.views,
            'is_viewed': blog.is_viewed_by(user.id)
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/get-all', methods=['GET'])
@jwt_required(optional=True)
@cache.cached(timeout=600, key_prefix=lambda: f"get_all_blogs:{request.full_path}")
def get_all_blogs():
    """Get all blogs with optional filtering"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        status_filter = request.args.get('status')
        creator_id = request.args.get('creator_id')
        
        query = Blog.query.filter_by(archived=False).filter(Blog.status != BlogStatus.DRAFT).order_by(Blog.created_at.desc())
        if creator_id:
            query = query.filter_by(created_by=creator_id)
        
        if status_filter:
            try:
                status_enum = BlogStatus(status_filter)
                query = query.filter_by(status=status_enum)
            except ValueError:
                return jsonify({'error': 'Invalid status value. Valid values: draft, published, rejected'}), 400
        
        blogs = query.all()
        
        return jsonify({
            'blogs': [blog.to_dict(user.id if user else None) for blog in blogs]
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@blog_bp.route('/my-blogs', methods=['GET'])
@jwt_required()
def get_my_blogs():
    """Get blogs created by the current user"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blogs = Blog.query.filter_by(created_by=user.id).order_by(Blog.created_at.desc()).all()
        
        return jsonify({
            'blogs': [blog.to_dict(user.id) for blog in blogs]
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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
        
        if blog.is_liked_by(user.id):
            blog.remove_like(user.id)
            action = 'unliked'
        else:
            blog.add_like(user.id)
            action = 'liked'
        
        db.session.commit()
        delete_blog_cache()
        return jsonify({
            'message': f'Blog {action} successfully',
            'blog': blog.to_dict(user.id),
            'action': action
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/<int:blog_id>/comment', methods=['POST'])
@jwt_required()
def create_comment(blog_id):
    """Create a comment on a blog post"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        if blog.status != BlogStatus.PUBLISHED:
            return jsonify({'error': 'Comments can only be added to published blogs'}), 400
        
        comment_text = request.json.get('comment')
        if not comment_text:
            return jsonify({'error': 'Comment text is required'}), 400
        
        if len(comment_text.strip()) == 0:
            return jsonify({'error': 'Comment cannot be empty'}), 400
        
        comment = Comment(
            comment=comment_text.strip(),
            commented_by=user.id,
            blog_id=blog_id
        )
        db.session.add(comment)
        db.session.commit()
        delete_blog_cache()
        return jsonify({
            'message': 'Comment created successfully',
            'comment': comment.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/comment/<int:comment_id>', methods=['PATCH'])
@jwt_required()
def edit_comment(comment_id):
    """Edit a comment"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        comment = Comment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404
        
        if comment.commented_by != user.id:
            return jsonify({'error': 'You can only edit your own comments'}), 403
        
        new_comment_text = request.json.get('comment')
        if not new_comment_text:
            return jsonify({'error': 'Comment text is required'}), 400
        
        if len(new_comment_text.strip()) == 0:
            return jsonify({'error': 'Comment cannot be empty'}), 400
        
        comment.comment = new_comment_text.strip()
        db.session.commit()
        delete_blog_cache()
        return jsonify({
            'message': 'Comment updated successfully',
            'comment': comment.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/comment/<int:comment_id>', methods=['DELETE'])
@jwt_required()
def delete_comment(comment_id):
    """Delete a comment"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        comment = Comment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404
        
        if comment.commented_by != user.id and user.role != UserRole.ADMIN:
            return jsonify({'error': 'You can only delete your own comments'}), 403
        
        db.session.delete(comment)
        db.session.commit()
        delete_blog_cache()
        return jsonify({
            'message': 'Comment deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@blog_bp.route('/image-embedding', methods=['POST'])
@jwt_required()
@creator_required
def blog_image_embedding():
    """Embed images in blog posts"""
    try:
        image_files = request.files.getlist('images')
        if not image_files:
            return jsonify({'error': 'No images provided'}), 400
        
        images = {}
        for image_file in image_files:
            image_path = None
            if image_file and image_file.filename != '':
                if not allowed_file(image_file.filename):
                    return jsonify({'error': 'Invalid file type. Allowed types: png, jpg, jpeg, gif, webp'}), 400
            
            headers = {
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
            }
            files = {
                "file": (image_file.filename, image_file.stream, image_file.content_type)
            }
            response = requests.post(CLOUDFLARE_IMAGE_URL, headers=headers, files=files)
            if response.status_code == 200:
                image_path = response.json()['result']['variants'][0]
                images[image_file.filename] = image_path
            else:
                return jsonify({'error': 'Image Embedding failed'}), 400
            
        return jsonify({'message': 'Images embedded successfully', 'images': images}), 200
    
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
    
    
@blog_bp.route('/comment/<int:comment_id>/hide', methods=['PATCH'])
@jwt_required()
@creator_required
def hide_blog_comment(comment_id):
    """Creator hides ANY comment on THEIR blog (soft hide)"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        comment = Comment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404
        
        blog = Blog.query.get(comment.blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # ensure the creator owns the blog
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only hide comments on your own blogs'}), 403
        
        comment.is_hidden = True
        db.session.commit()
        delete_blog_cache()
        
        return jsonify({'message': 'Comment hidden successfully'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500



@blog_bp.route('/comment/<int:comment_id>/unhide', methods=['PATCH'])
@jwt_required()
@creator_required
def unhide_blog_comment(comment_id):
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        comment = Comment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404
        
        blog = Blog.query.get(comment.blog_id)
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only unhide comments on your own blogs'}), 403
        
        comment.is_hidden = False
        db.session.commit()
        delete_blog_cache()
        
        return jsonify({'message': 'Comment unhidden successfully'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500



@blog_bp.route('/comment/<int:comment_id>/creator-delete', methods=['DELETE'])
@jwt_required()
@creator_required
def creator_delete_blog_comment(comment_id):
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        comment = Comment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404
        
        blog = Blog.query.get(comment.blog_id)
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only delete comments on your own blogs'}), 403
        
        db.session.delete(comment)
        db.session.commit()
        delete_blog_cache()
        
        return jsonify({'message': 'Comment deleted successfully'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500



@blog_bp.route('/<int:blog_id>/toggle-comments', methods=['POST'])
@jwt_required()
@creator_required
def toggle_blog_comments(blog_id):
    """Toggle show_comments for a blog (creator only)"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        blog = Blog.query.get(blog_id)
        if not blog:
            return jsonify({'error': 'Blog not found'}), 404
        
        # Check if the user is the author of the blog
        if blog.created_by != user.id:
            return jsonify({'error': 'You can only modify your own blogs'}), 403
        
        # Toggle the show_comments field
        blog.show_comments = not blog.show_comments
        db.session.commit()
        delete_blog_cache()
        
        return jsonify({
            'message': f'Comments {"enabled" if blog.show_comments else "disabled"} successfully',
            'show_comments': blog.show_comments
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500