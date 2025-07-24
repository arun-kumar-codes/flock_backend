import os
import time
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import Video, User, VideoStatus, VideoComment, UserRole
from app.utils import creator_required, allowed_file, admin_required, get_video_duration

video_bp = Blueprint('video', __name__)



@video_bp.route('/create', methods=['POST'])
@jwt_required()
@creator_required
def create_video():
    """Create a new video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        title = request.form.get('title')
        description = request.form.get('description')
        video = request.files.get('video')
        thumbnail = request.files.get('thumbnail')
        
        if not title or not video:
            return jsonify({'error': 'Title and video file are required'}), 400
        
        if len(title) > 200:
            return jsonify({'error': 'Title must be less than 200 characters'}), 400
        
        # Check if user has already uploaded 5 videos
        user_videos_count = Video.query.filter_by(created_by=user.id).count()
        if user_videos_count >= 5:
            return jsonify({'error': 'You can only upload a maximum of 5 videos'}), 400
        
        # Handle video upload
        if video.filename == '':
            return jsonify({'error': 'No video file selected'}), 400
        
        # Check if video file type is allowed
        allowed_video_types = {'mp4', 'mov'}
        if not video.filename.lower().split('.')[-1] in allowed_video_types:
            return jsonify({'error': 'Invalid video file type, allowed types: mp4, mov'}), 400
        
        # Create upload directory if it doesn't exist
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'videos')
        os.makedirs(upload_folder, exist_ok=True)
        
        # Secure the filename
        filename = secure_filename(video.filename)
        timestamp = int(time.time())
        filename = f"{timestamp}_{filename}"
        file_path = os.path.join(upload_folder, filename)
        
        # Save video file temporarily to check duration and size
        video.save(file_path)
        
        # Get video format
        format_type = filename.split('.')[-1].upper()
        
        # Get video duration
        duration = get_video_duration(file_path)
        
        # Check video duration (10 minutes = 600 seconds)
        if duration and duration > 600:
            # Remove the file if duration is too long
            os.remove(file_path)
            return jsonify({'error': 'Video duration must be less than 10 minutes'}), 400
        
        # Check file size (250 MB = 250 * 1024 * 1024 bytes)
        file_size = os.path.getsize(file_path)
        max_file_size = 250 * 1024 * 1024  # 250 MB in bytes
        if file_size > max_file_size:
            # Remove the file if size is too large
            os.remove(file_path)
            return jsonify({'error': 'Video file size must be less than 250 MB'}), 400
        
        # Store the relative path for database
        video_path = f"static/uploads/videos/{filename}"
        
        # Handle thumbnail upload
        thumbnail_url = None
        if thumbnail and thumbnail.filename != '':
            if not allowed_file(thumbnail.filename):
                return jsonify({'error': 'Invalid thumbnail file type. Allowed types: png, jpg, jpeg, gif, webp'}), 400
            
            # Create thumbnail upload directory if it doesn't exist
            thumbnail_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'thumbnails')
            os.makedirs(thumbnail_folder, exist_ok=True)
            
            # Secure the filename and save the thumbnail file
            thumbnail_filename = secure_filename(thumbnail.filename)
            thumbnail_filename = f"{timestamp}_{thumbnail_filename}"
            thumbnail_path = os.path.join(thumbnail_folder, thumbnail_filename)
            thumbnail.save(thumbnail_path)
            
            # Store the relative path for database
            thumbnail_path = f"static/uploads/thumbnails/{thumbnail_filename}"
        
        # Create new video with draft status
        video = Video(
            title=title,
            description=description,
            video=video_path,
            thumbnail=thumbnail_path,
            created_by=user.id,
            format=format_type,
            duration=duration
        )
        db.session.add(video)
        db.session.commit()
        
        return jsonify({
            'message': 'Video created successfully',
            'video': video.to_dict(user.id)
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>', methods=['PATCH'])
@jwt_required()
@creator_required
def update_video(video_id):
    """Update a video (title, description, thumbnail) - only draft or rejected videos"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Check if the user is the creator of the video
        if video.created_by != user.id:
            return jsonify({'error': 'You can only update your own videos'}), 403
        
        # Check if video can be updated (draft or rejected status only)
        if video.status not in [VideoStatus.DRAFT, VideoStatus.REJECTED]:
            return jsonify({'error': 'Only draft or rejected videos can be updated'}), 400
        
        # Get form data for updates
        title = request.form.get('title')
        description = request.form.get('description')
        thumbnail = request.files.get('thumbnail')
        
        # Update fields if provided
        if title:
            if len(title) > 200:
                return jsonify({'error': 'Title must be less than 200 characters'}), 400
            video.title = title
        
        if description is not None:
            video.description = description
        
        # Handle thumbnail update
        if thumbnail and thumbnail.filename != '':
            if not allowed_file(thumbnail.filename):
                return jsonify({'error': 'Invalid thumbnail type. Allowed types: png, jpg, jpeg, gif, webp'}), 400
            
            # Delete old thumbnail if it exists
            if video.thumbnail:
                old_thumbnail_path = os.path.join(current_app.root_path, video.thumbnail)
                if os.path.exists(old_thumbnail_path):
                    os.remove(old_thumbnail_path)
            
            # Create thumbnail upload directory if it doesn't exist
            thumbnail_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'thumbnails')
            os.makedirs(thumbnail_folder, exist_ok=True)
            
            # Secure the filename and save the thumbnail file
            thumbnail_filename = secure_filename(thumbnail.filename)
            timestamp = int(time.time())
            thumbnail_filename = f"{timestamp}_{thumbnail_filename}"
            thumbnail_path = os.path.join(thumbnail_folder, thumbnail_filename)
            thumbnail.save(thumbnail_path)
            
            # Store the relative path for database
            video.thumbnail = f"static/uploads/thumbnails/{thumbnail_filename}"
        
        if video.status == VideoStatus.REJECTED:
            video.status = VideoStatus.DRAFT
        
        db.session.commit()
        
        return jsonify({
            'message': 'Video updated successfully',
            'video': video.to_dict(user.id)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/approve', methods=['PATCH'])
@jwt_required()
@admin_required
def approve_video(video_id):
    """Approve a video by admin"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.status != VideoStatus.PENDING_APPROVAL:
            return jsonify({'error': 'Only pending videos can be approved'}), 400
        
        if video.approve():
            db.session.commit()
            return jsonify({
                'message': 'Video approved successfully',
                'video': video.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to approve video'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/reject', methods=['PATCH'])
@jwt_required()
@admin_required
def reject_video(video_id):
    """Reject a video by admin"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.status != VideoStatus.PENDING_APPROVAL:
            return jsonify({'error': 'Only pending videos can be rejected'}), 400
        
        if video.reject():
            db.session.commit()
            return jsonify({
                'message': 'Video rejected successfully',
                'video': video.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to reject video'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/archive', methods=['PATCH'])
@jwt_required()
@creator_required
def archive_video(video_id):
    """Archive a video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Check if the user is the creator of the video
        if video.created_by != user.id:
            return jsonify({'error': 'You can only archive your own videos'}), 403
        
        if video.archive():
            db.session.commit()
            return jsonify({
                'message': 'Video archived successfully',
                'video': video.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to archive video'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/unarchive', methods=['PATCH'])
@jwt_required()
@creator_required
def unarchive_video(video_id):
    """Unarchive a video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Check if the user is the creator of the video
        if video.created_by != user.id:
            return jsonify({'error': 'You can only unarchive your own videos'}), 403
        
        if video.unarchive():
            db.session.commit()
            return jsonify({
                'message': 'Video unarchived successfully',
                'video': video.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to unarchive video'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/send-for-approval', methods=['PATCH'])
@jwt_required()
@creator_required
def send_video_for_approval(video_id):
    """Send a video for admin approval"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Check if the user is the creator of the video
        if video.created_by != user.id:
            return jsonify({'error': 'You can only send your own videos for approval'}), 403
        
        if video.status != VideoStatus.DRAFT:
            return jsonify({'error': 'Only draft videos can be sent for approval'}), 400
        
        if video.send_for_approval():
            db.session.commit()
            return jsonify({
                'message': 'Video sent for approval successfully',
                'video': video.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to send video for approval'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>', methods=['GET'])
@jwt_required()
def get_video(video_id):
    """Get a specific video by ID"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        return jsonify({
            'video': video.to_dict(user.id)
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/get-all', methods=['GET'])
@jwt_required()
def get_all_videos():
    """Get all published videos with pagination"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        # Get query parameters
        status_filter = request.args.get('status')
        
        # Build query - exclude archived videos and draft videos
        query = Video.query.filter_by(archived=False).filter(Video.status != VideoStatus.DRAFT)
        
        # Apply status filter if provided
        if status_filter:
            # Convert string to enum value
            try:
                status_enum = VideoStatus(status_filter)
                query = query.filter_by(status=status_enum)
            except ValueError:
                return jsonify({'error': 'Invalid status value. Valid values: draft, pending_approval, published, rejected'}), 400
        
        videos = query.all()
        videos_list = [video.to_dict(user.id) for video in videos]
        
        return jsonify({
            'videos': videos_list
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/my-videos', methods=['GET'])
@jwt_required()
@creator_required
def get_my_videos():
    """Get all videos created by the current creator(user)"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        videos = Video.query.filter_by(created_by=user.id).order_by(Video.created_at.desc()).all()
        videos_list = [video.to_dict(user.id) for video in videos]
        
        return jsonify({
            'videos': videos_list
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/toggle-like', methods=['POST'])
@jwt_required()
def toggle_like_video(video_id):
    """Toggle like/unlike a video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.status != VideoStatus.PUBLISHED:
            return jsonify({'error': 'Only published videos can be liked'}), 400
        
        if video.is_liked_by(user.id):
            video.remove_like(user.id)
            message = 'Video unliked successfully'
        else:
            video.add_like(user.id)
            message = 'Video liked successfully'
        
        db.session.commit()
        
        return jsonify({
            'message': message,
            'likes': video.likes,
            'is_liked': video.is_liked_by(user.id)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/comment', methods=['POST'])
@jwt_required()
def create_video_comment(video_id):
    """Create a comment on a video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.status != VideoStatus.PUBLISHED:
            return jsonify({'error': 'Only published videos can be commented on'}), 400
        
        comment_text = request.json.get('comment')
        if not comment_text:
            return jsonify({'error': 'Comment text is required'}), 400
        
        if len(comment_text.strip()) == 0:
            return jsonify({'error': 'Comment cannot be empty'}), 400
        
        comment = VideoComment(
            comment=comment_text.strip(),
            commented_by=user.id,
            video_id=video_id
        )
        db.session.add(comment)
        db.session.commit()
        
        return jsonify({
            'message': 'Comment created successfully',
            'comment': comment.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/comment/<int:comment_id>', methods=['PATCH'])
@jwt_required()
def edit_video_comment(comment_id):
    """Edit a video comment"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        comment = VideoComment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404
        
        # Check if the user is the commenter
        if comment.commented_by != user.id:
            return jsonify({'error': 'You can only edit your own comments'}), 403
        
        comment_text = request.json.get('comment')
        if not comment_text:
            return jsonify({'error': 'Comment text is required'}), 400
        
        if len(new_comment_text.strip()) == 0:
            return jsonify({'error': 'Comment cannot be empty'}), 400
        
        comment.comment = comment_text.strip()
        db.session.commit()
        
        return jsonify({
            'message': 'Comment updated successfully',
            'comment': comment.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/comment/<int:comment_id>', methods=['DELETE'])
@jwt_required()
def delete_video_comment(comment_id):
    """Delete a video comment"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        comment = VideoComment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404
        
        # Check if the user is the commenter
        if comment.commented_by != user.id:
            return jsonify({'error': 'You can only delete your own comments'}), 403
        
        db.session.delete(comment)
        db.session.commit()
        
        return jsonify({
            'message': 'Comment deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500 