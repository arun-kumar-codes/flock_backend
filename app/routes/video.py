import os
import requests
import tempfile
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db, cache
from app.models import Video, User, VideoStatus, VideoComment, VideoWatchTime, UserRole
from app.utils import creator_required, admin_required, get_video_duration, transcode_video, get_trending_videos, delete_video_cache

video_bp = Blueprint('video', __name__)


CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_STREAM_URL = os.getenv('CLOUDFLARE_STREAM_URL')


@video_bp.route('/create', methods=['POST'])
@jwt_required()
@creator_required
def create_video():
    """Create a new video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        video_file = request.files.get('video')
        title = request.form.get('title')

        if not video_file or not title:
            return jsonify({'error': 'Missing title or video'}), 400
        if len(title) > 200:
            return jsonify({'error': 'Title must be less than 200 characters'}), 400 
       
        # Check if user has already uploaded 5 videos
        # user_videos_count = Video.query.filter_by(created_by=user.id).count()
        # if user_videos_count >= 5:
        #     return jsonify({'error': 'You can only upload a maximum of 5 videos'}), 400
        
        # Check if video file type is allowed
        allowed_video_types = {'mp4', 'mov'}
        ext = video_file.filename.lower().split('.')[-1]
        if ext not in allowed_video_types:
            return jsonify({'error': 'Invalid video file type, allowed types: mp4, mov'}), 400

        # Save uploaded video to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp:
            video_file.save(temp.name)

            # Validate video duration
            duration = get_video_duration(temp.name)
            if duration > 600:
                return jsonify({'error': 'Video too long (max 10 mins)'}), 400
            if os.path.getsize(temp.name) > 250 * 1024 * 1024:
                return jsonify({'error': 'File too large (max 250 MB)'}), 400

            # Transcode with FFmpeg
            transcoded_path = temp.name.replace(f".{ext}", "_transcoded.mp4")
            transcode_video(temp.name, transcoded_path)

            # Custom filename: username_datetime
            now_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            clean_username = ''.join(c for c in user.username if c.isalnum() or c in ('-', '_'))
            upload_filename = f"{clean_username}_{now_str}.{ext}"

            # Upload to Cloudflare Stream
            with open(transcoded_path, 'rb') as f:
                response = requests.post(
                    CLOUDFLARE_STREAM_URL,
                    headers={
                        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
                    },
                    files={"file": (upload_filename, f)}
                )

            if response.status_code != 200:
                return jsonify({'error': 'Video Upload failed'}), 400

            cloudflare_data = response.json()
            playback_url = f"https://videodelivery.net/{cloudflare_data['result']['uid']}/watch"

            # Save video info to DB
            video = Video(
                title=title,
                description=request.form.get('description'),
                duration=duration,
                video=playback_url,
                thumbnail=cloudflare_data['result']['thumbnail'],
                created_by=user.id
            )
            db.session.add(video)
            db.session.commit()
            delete_video_cache()

        return jsonify({'message': 'Video uploaded successfully', 'url': playback_url}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@video_bp.route('/<int:video_id>', methods=['PATCH'])
@jwt_required()
@creator_required
def update_video(video_id):
    """Update a video (title, description) - only draft or rejected videos"""
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
        title = request.json.get('title')
        description = request.json.get('description')
        
        # Update fields if provided
        if title:
            if len(title) > 200:
                return jsonify({'error': 'Title must be less than 200 characters'}), 400
            video.title = title
        
        if description is not None:
            video.description = description

        if video.status == VideoStatus.REJECTED:
            video.status = VideoStatus.DRAFT
        
        db.session.commit()
        delete_video_cache()
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
            delete_video_cache()
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
            delete_video_cache()
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
            delete_video_cache()
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
            delete_video_cache()
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
            delete_video_cache()
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
@jwt_required(optional=True)
@cache.cached(timeout=300, key_prefix=lambda: f"get_all_videos:{request.full_path}")
def get_all_videos():
    """Get all published videos with pagination"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        # Get query parameters
        status_filter = request.args.get('status')
        trending = request.args.get('trending')
        creator_id = request.args.get('creator_id')
        
        if trending:
            trending_videos = get_trending_videos()
            return jsonify({
                'videos': [video.to_dict(user.id if user else None) for video in trending_videos]
            }), 200
        
        # Build query - exclude archived videos and draft videos
        query = Video.query.filter_by(archived=False).filter(Video.status != VideoStatus.DRAFT).order_by(Video.created_at.desc())
        if creator_id:
            query = query.filter_by(created_by=creator_id)
        # Apply status filter if provided
        if status_filter:
            # Convert string to enum value
            try:
                status_enum = VideoStatus(status_filter)
                query = query.filter_by(status=status_enum)
            except ValueError:
                return jsonify({'error': 'Invalid status value. Valid values: draft, pending_approval, published, rejected'}), 400
        
        videos = query.all()
        print(videos)
        videos_list = [video.to_dict(user.id if user else None) for video in videos]
        
        return jsonify({
            'videos': videos_list
        }), 200
        
    except Exception as e:
        print(e)
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
        delete_video_cache()
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
        delete_video_cache()
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
        
        if len(comment_text.strip()) == 0:
            return jsonify({'error': 'Comment cannot be empty'}), 400
        
        comment.comment = comment_text.strip()
        db.session.commit()
        delete_video_cache()
        return jsonify({
            'message': 'Comment updated successfully',
            'comment': comment.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/view', methods=['POST'])
@jwt_required()
def add_video_view(video_id):
    """Add a view to a video by a user"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.status != VideoStatus.PUBLISHED:
            return jsonify({'error': 'Only published videos can be viewed'}), 400
        
        # Add view for the user
        video.add_view(user.id)
        db.session.commit()
        delete_video_cache()
        return jsonify({
            'message': 'View added successfully',
            'views': video.views,
            'is_viewed': video.is_viewed_by(user.id)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/watch-time', methods=['POST'])
@jwt_required()
def add_video_watch_time(video_id):
    """Add watch time for a video by a user (only viewers can add watch time)"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        # Only viewers can add watch time
        if user.role != UserRole.VIEWER:
            return jsonify({'error': 'Only viewers can add watch time'}), 403
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.status != VideoStatus.PUBLISHED:
            return jsonify({'error': 'Only published videos can have watch time'}), 400
        
        # Get watch time from request payload
        watch_time_seconds = request.json.get('watch_time')
        if not watch_time_seconds or not isinstance(watch_time_seconds, (int, float)) or watch_time_seconds <= 0:
            return jsonify({'error': 'Valid watch_time (positive number) is required in payload'}), 400
        
        if watch_time_seconds <= 0.9 * video.duration:
            return jsonify({'error': 'Watch time must be greater than 90% of video duration'}), 400
        if watch_time_seconds > video.duration:
            # return jsonify({'error': 'Watch time cannot be greater than video duration'}), 400
            watch_time_seconds = video.duration
        
        # Add watch time to the video
        video.add_watch_time(user.id, int(watch_time_seconds))
        db.session.commit()
        delete_video_cache()
        return jsonify({
            'message': 'Watch time added successfully',
            'total_watch_time': video.total_watch_time,
            'total_watch_time_formatted': video.format_watch_time(video.total_watch_time),
            'user_watch_time': video.get_user_watch_time(user.id),
            'user_watch_time_formatted': video.format_watch_time(video.get_user_watch_time(user.id))
        }), 200
        
    except Exception as e:
        print(e)
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


@video_bp.route('/<int:video_id>/watch-time', methods=['GET'])
@jwt_required()
def get_video_watch_time(video_id):
    """Get watch time statistics for a video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.status != VideoStatus.PUBLISHED:
            return jsonify({'error': 'Only published videos can have watch time'}), 400
        
        # Get all watch time entries for this video
        watch_times = VideoWatchTime.query.filter_by(video_id=video_id).all()
        
        return jsonify({
            'video_id': video_id,
            'total_watch_time': video.total_watch_time,
            'total_watch_time_formatted': video.format_watch_time(video.total_watch_time),
            'user_watch_time': video.get_user_watch_time(user.id),
            'user_watch_time_formatted': video.format_watch_time(video.get_user_watch_time(user.id)),
            'watch_time_entries': [wt.to_dict() for wt in watch_times],
            'total_viewers': len(watch_times)
        }), 200
        
    except Exception as e:
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
        delete_video_cache()
        return jsonify({
            'message': 'Comment deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500 