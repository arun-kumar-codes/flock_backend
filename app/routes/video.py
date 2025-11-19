import os, uuid
import json
import requests
import tempfile
from datetime import datetime, timezone
from dateutil.parser import isoparse
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from tusclient import client
import time
from app.tasks.tasks import upload_video_task

from app import db, cache
from app.models import Video, User, VideoStatus, VideoComment, VideoWatchTime, UserRole
from app.utils import creator_required, admin_required, get_video_duration, transcode_video, delete_video_cache
from app.models.upload_session import UploadSession

video_bp = Blueprint('video', __name__)


CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_STREAM_URL = os.getenv('CLOUDFLARE_STREAM_URL')
CLOUDFLARE_IMAGE_URL = os.getenv('CLOUDFLARE_IMAGE_URL')
CLOUDFLARE_ACCOUNT_ID = 'f8169ac512b63c3871439a3fc8a06726'


@video_bp.route('/create', methods=['POST'])
@jwt_required()
@creator_required
def create_video():
    """Create a new video asynchronously using TUS protocol"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()

        video_file = request.files.get('video')
        thumbnail_file = request.files.get('thumbnail')
        title = request.form.get('title')
        scheduled_at_str = request.form.get('scheduled_at')

        if not video_file or not title:
            return jsonify({'error': 'Missing title or video'}), 400

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

        # Choose a writable path within your app directory
        UPLOAD_TMP_DIR = os.path.join(os.getcwd(), "uploads_tmp")
        os.makedirs(UPLOAD_TMP_DIR, exist_ok=True)

        temp_video = os.path.join(UPLOAD_TMP_DIR, f"{uuid.uuid4()}")
        with open(temp_video, 'wb') as f:
            chunk_size = 1024 * 1024 * 100  # 100MB
            while True:
                chunk = video_file.stream.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)

        temp_thumb = None
        if thumbnail_file:
            temp_thumb = os.path.join(UPLOAD_TMP_DIR, f"{uuid.uuid4()}")
            thumbnail_file.save(temp_thumb)

        # Extract form data
        video_data = {
            "title": title,
            "description": request.form.get("description"),
            "keywords": json.loads(request.form.get("keywords", "[]")),
            "locations": json.loads(request.form.get("locations", "[]")),
            "is_draft": request.form.get("is_draft", "false").lower() == "true",
            "is_scheduled": is_scheduled,
            "scheduled_at": scheduled_at,
            "age_restricted": request.form.get("age_restricted", "false").lower() == "true",
            "brand_tags": json.loads(request.form.get("brand_tags", "[]")),
            "paid_promotion": request.form.get("paid_promotion", "false").lower() == "true"
        }

        # Enqueue background task with TUS upload
        task = upload_video_task.apply_async(
            args=[user.id, video_data, temp_video, temp_thumb if temp_thumb else None]
        )

        return jsonify({
            "message": "Video upload started in background using TUS protocol",
            "task_id": task.id,
            "info": "Upload will resume automatically if interrupted"
        }), 202

    except Exception as e:
        import traceback
        traceback.print_exc()
        if 'temp_video' in locals() and os.path.exists(temp_video.name):
            os.remove(temp_video.name)
        if 'temp_thumb' in locals() and temp_thumb and os.path.exists(temp_thumb.name):
            os.remove(temp_thumb.name)
        return jsonify({'error': str(e)}), 500



@video_bp.route('/task-status/<task_id>', methods=['GET', 'OPTIONS'])
@jwt_required()
def get_task_status(task_id):
    """Get the status of a background task"""
    try:
        from app import celery_app

        print(f"=== CHECKING TASK STATUS ===")
        print(f"Task ID: {task_id}")

        task = celery_app.AsyncResult(task_id)

        print(f"Task State: {task.state}")
        print(f"Task Info: {task.info}")

        if task.state == 'PENDING':
            response = {
                'state': task.state,
                'status': 'Task is waiting to start...'
            }
        elif task.state == 'STARTED':
            response = {
                'state': task.state,
                'status': 'Video is uploading...'
            }
        elif task.state == 'SUCCESS':
            # detect cancellation result
            if isinstance(task.result, dict) and task.result.get("cancelled"):
                response = {
                    "state": "CANCELLED",
                    "status": "Upload cancelled by user"
                }
            else:
                response = {
                    'state': task.state,
                    'status': 'Upload completed successfully!',
                    'result': task.result
                }
        elif task.state == 'FAILURE':
            # Detect cancellation
            if task.info == {"cancelled": True} or \
               (isinstance(task.info, dict) and task.info.get("error") == "cancelled"):
                response = {
                    "state": "CANCELLED",
                    "status": "Upload cancelled by user"
                }
            else:
                response = {
                    'state': 'FAILURE',
                    'status': 'Upload failed',
                    'error': str(task.info)
                }
        # CASE FOR REVOKED
        elif task.state == 'REVOKED':
            response = {
                'state': 'CANCELLED',
                'status': 'Upload cancelled by user'
            }
        else:
            response = {
                'state': task.state,
                'status': str(task.info)
            }

        print(f"Response: {response}")
        print("=" * 30)

        return jsonify(response), 200
    except Exception as e:
        print(f"ERROR in get_task_status: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    
@video_bp.route("/cancel-upload/<task_id>", methods=["POST"])
@jwt_required()
@creator_required
def cancel_upload(task_id):
    """Cancel an active TUS upload for a video"""
    try:
        session = UploadSession.query.filter_by(id=task_id).first()
        if not session:
            return jsonify({"error": "No active upload session"}), 404

        # Mark as cancelled
        session.cancelled = True
        db.session.commit()
        
        print(f"✅ Upload session {task_id} marked as cancelled")

        # Try to revoke the Celery task
        try:
            from app import celery_app
            celery_app.control.revoke(task_id, terminate=True, signal='SIGKILL')
            print(f"✅ Celery task {task_id} revoked")
        except Exception as e:
            print(f"⚠️ Could not revoke Celery task: {str(e)}")

        # If a TUS upload already started, delete it on Cloudflare
        if session.tus_url:
            try:
                response = requests.delete(
                    session.tus_url,
                    headers={
                        "Tus-Resumable": "1.0.0",
                        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
                    },
                    timeout=5
                )
                print(f"🗑️ Cloudflare TUS deletion response: {response.status_code}")
            except Exception as e:
                print(f"⚠️ Error deleting TUS upload from Cloudflare: {str(e)}")
        
        return jsonify({"message": "Upload cancelled successfully"}), 200
        
    except Exception as e:
        print(f"❌ Error in cancel_upload: {str(e)}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@video_bp.route('/<int:video_id>', methods=['PATCH'])
@jwt_required()
@creator_required
def update_video(video_id):
    """Update a video (title, description, keywords, thumbnail, age restriction)"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404

        if video.created_by != user.id:
            return jsonify({'error': 'You can only update your own videos'}), 403

        if video.status not in [VideoStatus.DRAFT, VideoStatus.PUBLISHED, VideoStatus.REJECTED]:
            return jsonify({'error': 'Check video status'}), 400

        # Handle form data (frontend must send FormData, not JSON)
        title = request.form.get('title')
        description = request.form.get('description')
        keywords = request.form.get('keywords')  # JSON string or comma separated
        locations = request.form.get('locations')
        age_restricted = request.form.get('age_restricted')  # "true"/"false"
        thumbnail_file = request.files.get('thumbnail')
        paid_promotion = request.form.get("paid_promotion")
        brand_tags = request.form.get("brand_tags")

        if title:
            if len(title) > 200:
                return jsonify({'error': 'Title must be less than 200 characters'}), 400
            video.title = title

        if description is not None:
            video.description = description

        if keywords is not None:
            try:
                # If frontend sends JSON.stringify([...])
                keywords_list = json.loads(keywords) if isinstance(keywords, str) else keywords
                if not isinstance(keywords_list, list):
                    keywords_list = []
            except Exception:
                # If comma separated
                keywords_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]
            video.set_keywords(keywords_list)
        
        if locations is not None:
            try:
                # If frontend sends JSON.stringify([...])
                locations_list = json.loads(locations) if isinstance(locations, str) else locations
                if not isinstance(locations_list, list):
                    locations_list = []
            except Exception:
                # If comma separated string
                locations_list = [loc.strip() for loc in locations.split(",") if loc.strip()]
            video.locations = locations_list

        if age_restricted is not None:
            video.age_restricted = str(age_restricted).lower() in ["true", "1", "yes"]
            
        if brand_tags is not None:
            try:
                brand_tags = json.loads(brand_tags)
                if not isinstance(brand_tags, list):
                    brand_tags = [brand_tags]
            except Exception:
                brand_tags = [b.strip() for b in brand_tags.split(',') if b.strip()]
            video.brand_tags = brand_tags

        if paid_promotion is not None:
            video.paid_promotion = str(paid_promotion).lower() in ["true", "1", "yes"]

        if thumbnail_file:
            thumb_ext = thumbnail_file.filename.lower().split('.')[-1]
            filename = f"thumb_update_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{thumb_ext}"

            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{thumb_ext}") as temp_thumb:
                thumbnail_file.save(temp_thumb.name)

                # Upload to Cloudflare
                with open(temp_thumb.name, "rb") as f_thumb:
                    thumb_response = requests.post(
                        CLOUDFLARE_IMAGE_URL,
                        headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
                        files={"file": (filename, f_thumb)},
                        timeout=30
                    )

            os.remove(temp_thumb.name)  # leanup temp file safely

            if thumb_response.status_code == 200:
                thumb_data = thumb_response.json()
                variants = thumb_data.get("result", {}).get("variants", [])
                if variants:
                    video.thumbnail = variants[0]
                    video.updated_at = datetime.utcnow()  # refresh timestamp
                else:
                    return jsonify({"error": "Invalid Cloudflare response format"}), 400
            else:
                print("Thumbnail upload failed:", thumb_response.text)
                return jsonify({"error": "Thumbnail upload failed"}), 400


        # Commit updates
        db.session.commit()
        delete_video_cache()

        return jsonify({
            "message": "Video updated successfully",
            "video": video.to_dict(user.id)
        }), 200

    except Exception as e:
        db.session.rollback()
        print("Error in update_video:", e)
        return jsonify({"error": "Internal server error"}), 500


@video_bp.route('/<int:video_id>/publish', methods=['PATCH'])
@jwt_required()
@creator_required
def publish_video(video_id):
    """Publish a video by creator"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.status != VideoStatus.DRAFT:
            return jsonify({'error': 'Only draft videos can be published'}), 400
        
        if video.publish():
            db.session.commit()
            delete_video_cache()
            return jsonify({
                'message': 'Video published successfully',
                'video': video.to_dict(user.id)
            }), 200
        else:
            return jsonify({'error': 'Failed to publish video'}), 400
            
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
        
        if video.status != VideoStatus.PUBLISHED:
            return jsonify({'error': 'Only published videos can be rejected'}), 400
        reason = request.json.get('reason')
        if not reason:
            return jsonify({'error': 'Reason is required'}), 400
        if video.reject(reason):
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


@video_bp.route('/<int:video_id>/delete', methods=['DELETE'])
@jwt_required()
@creator_required
def delete_video(video_id):
    """Delete a video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()

        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.created_by != user.id:
            return jsonify({'error': 'You can only delete your own videos'}), 403

        if video.delete():
            delete_video_cache()
            return jsonify({
                'message': 'Video deleted successfully'
            }), 200
        else:
            return jsonify({'error': 'Failed to delete video'}), 400
            
    except Exception as e:
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
        
        status_filter = request.args.get('status')
        creator_id = request.args.get('creator_id')
        
        query = Video.query.filter_by(archived=False).filter(Video.status != VideoStatus.DRAFT).order_by(Video.created_at.desc())
        if creator_id:
            query = query.filter_by(created_by=creator_id)
        if status_filter:
            try:
                status_enum = VideoStatus(status_filter)
                query = query.filter_by(status=status_enum)
            except ValueError:
                return jsonify({'error': 'Invalid status value. Valid values: draft, published, rejected'}), 400
        
        videos = query.all()
        videos_list = [video.to_dict(user.id if user else None) for video in videos]
        
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

        # prevent commenting when disabled
        if not video.show_comments:
            return jsonify({'error': 'Comments are disabled for this video'}), 403

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
        
        if user.role != UserRole.VIEWER:
            return jsonify({'error': 'Only viewers can add watch time'}), 403
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        if video.status != VideoStatus.PUBLISHED:
            return jsonify({'error': 'Only published videos can have watch time'}), 400
        
        watch_time_seconds = request.json.get('watch_time')
        if not watch_time_seconds or not isinstance(watch_time_seconds, (int, float)) or watch_time_seconds <= 0:
            return jsonify({'error': 'Valid watch_time (positive number) is required in payload'}), 400
        
        if watch_time_seconds <= 0.1 * video.duration:
            return jsonify({'error': 'Watch time must be greater than 10% of video duration'}), 400
        if watch_time_seconds > video.duration:
            # return jsonify({'error': 'Watch time cannot be greater than video duration'}), 400
            watch_time_seconds = video.duration
        
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
    
    
@video_bp.route('/comment/<int:comment_id>/creator-delete', methods=['DELETE'])
@jwt_required()
@creator_required
def creator_delete_comment(comment_id):
    """Creator can delete ANY comment on THEIR video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        comment = VideoComment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404

        video = Video.query.get(comment.video_id)
        # ensure the logged-in creator OWNS the video
        if video.created_by != user.id:
            return jsonify({'error': 'You can only manage comments on your own videos'}), 403

        db.session.delete(comment)
        db.session.commit()
        delete_video_cache()

        return jsonify({'message': 'Comment deleted by creator'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500



@video_bp.route('/comment/<int:comment_id>/hide', methods=['PATCH'])
@jwt_required()
@creator_required
def hide_video_comment(comment_id):
    """Creator can hide ANY comment on THEIR video"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()

        comment = VideoComment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404

        video = Video.query.get(comment.video_id)

        if video.created_by != user.id:
            return jsonify({'error': 'You can only hide comments on your own videos'}), 403

        comment.is_hidden = True
        db.session.commit()
        delete_video_cache()

        return jsonify({'message': 'Comment hidden successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500



@video_bp.route('/comment/<int:comment_id>/unhide', methods=['PATCH'])
@jwt_required()
@creator_required
def unhide_video_comment(comment_id):
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()

        comment = VideoComment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Comment not found'}), 404

        video = Video.query.get(comment.video_id)
        if video.created_by != user.id:
            return jsonify({'error': 'You can only unhide comments on your own videos'}), 403

        comment.is_hidden = False
        db.session.commit()
        delete_video_cache()

        return jsonify({'message': 'Comment unhidden', 'is_hidden': False}), 200

    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500



@video_bp.route('/<int:video_id>/toggle-comments', methods=['POST'])
@jwt_required()
@creator_required
def toggle_video_comments(video_id):
    """Toggle show_comments for a video (creator only)"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Check if the user is the creator of the video
        if video.created_by != user.id:
            return jsonify({'error': 'You can only modify your own videos'}), 403
        
        # Toggle the show_comments field
        video.show_comments = not video.show_comments
        db.session.commit()
        delete_video_cache()
        
        return jsonify({
            'message': f'Comments {"enabled" if video.show_comments else "disabled"} successfully',
            'show_comments': video.show_comments
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500 