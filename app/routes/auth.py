import os
from firebase_admin import auth as firebase_auth
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
import requests

from app import db
from app.models import User, UserRole, Invitation, Video, Blog, VideoStatus, BlogStatus
from app.utils import admin_required, creator_required, delete_video_cache
from app.utils import allowed_file, delete_blog_cache, delete_previous_image
import firebase_setup

auth_bp = Blueprint('auth', __name__)

RECAPTCHA_SECRET_KEY = os.getenv('RECAPTCHA_SECRET_KEY')
CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_IMAGE_URL = os.getenv('CLOUDFLARE_IMAGE_URL')


@auth_bp.route('/signup', methods=['POST'])
def signup():
    """User registration endpoint"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        captcha_token = data.get('captchaToken')
        
        if not username or not email or not password:
            return jsonify({'error': 'Username, email, and password are required'}), 400
        
        role = UserRole.VIEWER
        invitation = Invitation.query.filter_by(email=email).first()
        if invitation:
            role = UserRole.CREATOR
                
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": RECAPTCHA_SECRET_KEY,
                "response": captcha_token
            }
        )
        if not response.json().get('success'):
            return jsonify({'error': 'Invalid captcha'}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        user_role = UserRole(role)
        user = User(
            username=username,
            email=email,
            password=password,
            role=user_role
        )
        
        db.session.add(user)
        db.session.commit()
        
        response_data = {
            'user': user.to_dict()
        }
        
        return jsonify(response_data), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        id_token = request.json.get('idToken')
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get('email')

        is_new_user = False
        user = User.query.filter_by(email=email).first()
        if not user:
            invitation = Invitation.query.filter_by(email=email).first()
            if invitation:
                role = UserRole.CREATOR
            else:
                role = UserRole.VIEWER
            user = User(email=email, role=role)
            db.session.add(user)
            db.session.commit()
            is_new_user = True

        profile_complete = user.is_profile_complete()
        access_token = create_access_token(identity=user.email)
        refresh_token = create_refresh_token(identity=user.email)
        
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(),
            'profile_complete': profile_complete,
            'is_new_user': is_new_user
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    
@auth_bp.route('/complete-profile', methods=['PUT'])
@jwt_required()
def complete_profile():
    try:
        email = get_jwt_identity()
        username = request.json.get('username')
        password = request.json.get('password')
        
        if not username or not password:
            return jsonify({'error': 'All fields are required'}), 400
            
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({'error': 'Username already exists'}), 400
            
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        user.complete_profile(username, password)
        db.session.commit()
        
        return jsonify({
            'message': 'Profile completed successfully',
            'user': user.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    
@auth_bp.route('/update-profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user profile information (username and profile picture)"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        username = request.form.get('username')
        profile_picture_file = request.files.get('profile_picture')
        
        if username is None and profile_picture_file is None:
            return jsonify({'error': 'At least one field (username or profile_picture) is required'}), 400
            
        if username is not None:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user and existing_user.email != email:
                return jsonify({'error': 'Username already exists'}), 400
        
        profile_picture_path = None
        if profile_picture_file and profile_picture_file.filename != '':
            if not allowed_file(profile_picture_file.filename):
                return jsonify({'error': 'Invalid file type. Allowed types: png, jpg, jpeg, gif, webp'}), 400
            
            headers = {
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
               }
            files = {
                "file": (profile_picture_file.filename, profile_picture_file.stream, profile_picture_file.content_type)
            }
            response = requests.post(CLOUDFLARE_IMAGE_URL, headers=headers, files=files)
            if response.status_code == 200:
                delete_previous_image(user.profile_picture)
                profile_picture_path = response.json()['result']['variants'][0]
            else:
                return jsonify({'error': 'Image upload failed'}), 400
            
        user.update_profile(username=username, profile_picture=profile_picture_path)
        db.session.commit()
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': user.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    
@auth_bp.route('/login-password', methods=['POST'])
def login_password():
    """User login with password endpoint"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        identifier = data.get('username_or_email')
        password = data.get('password')
        captcha_token = data.get('captchaToken')
        
        if not identifier or not password:
            return jsonify({'error': 'Username/email and password are required'}), 400
        
        user = User.query.filter_by(email=identifier).first()
        if not user:
            user = User.query.filter_by(username=identifier).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid username/email or password'}), 400
        
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": RECAPTCHA_SECRET_KEY,
                "response": captcha_token
            }
        )
        if not response.json().get('success'):
            return jsonify({'error': 'Invalid captcha'}), 400 
        
        access_token = create_access_token(identity=user.email)
        refresh_token = create_refresh_token(identity=user.email)
        
        profile_complete = user.is_profile_complete()
        
        return jsonify({
            'message': 'Login successful', 
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(),
            'profile_complete': profile_complete
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh JWT access token"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        access_token = create_access_token(identity=user.email)
        
        return jsonify({
            'access_token': access_token
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user information using jwt identity"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'user': user.to_dict(),
            'profile_complete': user.is_profile_complete()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
    
@auth_bp.route('/all-users', methods=['GET'])
@jwt_required()
@admin_required
def get_all_users():
    """Get all users"""
    try:
        users = User.query.filter(User.role != UserRole.ADMIN).all()
        return jsonify({'users': [user.to_dict() for user in users]}), 200
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
    
@auth_bp.route('/all-creators', methods=['GET'])
@jwt_required(optional=True)
def get_all_creators():
    """Get all creators"""
    try:
        creators = User.query.filter(User.role == UserRole.CREATOR).all()
        return jsonify({'creators': [creator.to_dict() for creator in creators]}), 200
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
    
@auth_bp.route('/all-viewers', methods=['GET'])
@jwt_required()
@admin_required
def get_all_viewers():
    """Get all viewers"""
    try:
        viewers = User.query.filter(User.role == UserRole.VIEWER).all()
        return jsonify({'viewers': [viewer.to_dict() for viewer in viewers]}), 200
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
    
@auth_bp.route('/delete-user/<int:id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_user(id):
    """Delete user"""
    try:
        user = User.query.filter_by(id=id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        db.session.delete(user)
        db.session.commit()
        return jsonify({'message': 'User deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/creator-data', methods=['GET'])
@jwt_required()
@creator_required
def get_creator_data():
    """Get comprehensive creator data including videos, blogs, likes, views, etc."""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        videos = Video.query.filter_by(created_by=user.id).all()
        
        blogs = Blog.query.filter_by(created_by=user.id).all()
        
        total_videos = len(videos)
        published_videos = len([v for v in videos if v.status == VideoStatus.PUBLISHED])
        draft_videos = len([v for v in videos if v.status == VideoStatus.DRAFT])
        rejected_videos = len([v for v in videos if v.status == VideoStatus.REJECTED])
        archived_videos = len([v for v in videos if v.archived])
        
        total_blogs = len(blogs)
        published_blogs = len([b for b in blogs if b.status == BlogStatus.PUBLISHED])
        draft_blogs = len([b for b in blogs if b.status == BlogStatus.DRAFT])
        rejected_blogs = len([b for b in blogs if b.status == BlogStatus.REJECTED])
        archived_blogs = len([b for b in blogs if b.archived])
        
        total_video_likes = sum(video.likes for video in videos)
        total_video_views = sum(video.views for video in videos)
        total_video_watch_time = sum(video.total_watch_time for video in videos)
        
        total_blog_likes = sum(blog.likes for blog in blogs)
        total_blog_views = sum(blog.views for blog in blogs)
        
        creator_data = {
            'user': user.to_dict(),
            'statistics': {
                'videos': {
                    'total': total_videos,
                    'published': published_videos,
                    'draft': draft_videos,
                    'rejected': rejected_videos,
                    'archived': archived_videos,
                    'total_likes': total_video_likes,
                    'total_views': total_video_views,
                    'total_watch_time': total_video_watch_time
                },
                'blogs': {
                    'total': total_blogs,
                    'published': published_blogs,
                    'draft': draft_blogs,
                    'rejected': rejected_blogs,
                    'archived': archived_blogs,
                    'total_likes': total_blog_likes,
                    'total_views': total_blog_views
                },
                'overall': {
                    'total_content': total_videos + total_blogs,
                    'total_likes': total_video_likes + total_blog_likes,
                    'total_views': total_video_views + total_blog_views
                }
            }
        }
        
        return jsonify(creator_data), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/follow/<int:user_id>', methods=['POST'])
@jwt_required()
def follow_user(user_id):
    """Follow a user/creator"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user_to_follow = User.query.get(user_id)
        
        if not user_to_follow:
            return jsonify({'error': 'User to follow not found'}), 404
        
        if user.id == user_id:
            return jsonify({'error': 'Cannot follow yourself'}), 400
        
        if user.is_following(user_to_follow):
            return jsonify({'error': 'Already following this user'}), 400
        
        success = user.follow(user_to_follow)
        
        if success:
            db.session.commit()
            delete_video_cache()
            delete_blog_cache()
            return jsonify({
                'message': f'Successfully followed {user_to_follow.username}',
                'followed_user': user_to_follow.to_dict(),
            }), 200
        else:
            return jsonify({'error': 'Failed to follow user'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/unfollow/<int:user_id>', methods=['POST'])
@jwt_required()
def unfollow_user(user_id):
    """Unfollow a user/creator"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'Current user not found'}), 404
        
        user_to_unfollow = User.query.get(user_id)
        
        if not user_to_unfollow:
            return jsonify({'error': 'User to unfollow not found'}), 404
        
        if user.id == user_id:
            return jsonify({'error': 'Cannot unfollow yourself'}), 400
        
        if not user.is_following(user_to_unfollow):
            return jsonify({'error': 'Not following this user'}), 400
        
        success = user.unfollow(user_to_unfollow)
        
        if success:
            db.session.commit()
            delete_video_cache()
            delete_blog_cache()
            return jsonify({
                'message': f'Successfully unfollowed {user_to_unfollow.username}',
                'unfollowed_user': user_to_unfollow.to_dict()
            }), 200
        else:
            return jsonify({'error': 'Failed to unfollow user'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/followers', methods=['GET'])
@jwt_required()
def get_user_followers():
    """Get followers of a user"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        followers = user.get_followers()
        
        return jsonify({
            'followers': [follower.to_dict() for follower in followers],
            'followers_count': user.get_followers_count()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/following', methods=['GET'])
@jwt_required()
def get_user_following():
    """Get users that a user is following"""
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        following = user.get_following()
        
        return jsonify({
            'following': [followed.to_dict() for followed in following],
            'following_count': user.get_following_count()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
    
@auth_bp.route('/cache-clear', methods=['GET'])    
def cache_clear():
    delete_video_cache()
    delete_blog_cache()
    return jsonify({
        'success': 'Cache cleared'
    }), 200