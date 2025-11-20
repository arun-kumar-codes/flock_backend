import os
from firebase_admin import auth as firebase_auth
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, verify_jwt_in_request
import requests
import re
import tempfile
import mimetypes
from app import db
from app.models import User, UserRole, Invitation, Video, Blog, VideoStatus, BlogStatus
from app.utils import admin_required, creator_required, delete_video_cache
from app.utils import allowed_file, delete_blog_cache, delete_previous_image
from app.utils.email import send_reset_password_email
import secrets
from datetime import datetime, timedelta, date
import random
from urllib.parse import unquote
from app.utils.email import send_verification_email


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
        dob = data.get('dob') 
        captcha_token = data.get('recaptchaToken')
        
        if not username or not email or not password:
            return jsonify({'error': 'Username, email, and password are required'}), 400
        
        # DOB validation
        dob_value = None
        if dob:
            try:
                dob_value = datetime.strptime(dob, "%Y-%m-%d").date()
            except:
                return jsonify({'error': 'Invalid date format. Use DD-MM-YYYY'}), 400

            today = date.today()
            age = today.year - dob_value.year - ((today.month, today.day) < (dob_value.month, dob_value.day))

            if age < 13:
                return jsonify({'error': 'You must be at least 13 years old to use this service.'}), 400
            
        # Password strength validation
        password_pattern = re.compile(
            r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\'":\\|,.<>\/?])[A-Za-z\d!@#$%^&*()_+\-=\[\]{};\'":\\|,.<>\/?]{8,}$'
        )

        if not password_pattern.match(password):
            return jsonify({
                'error': (
                    'Password must be at least 8 characters long and include '
                    'an uppercase letter, lowercase letter, number, and special character.'
                )
            }), 400
        
        # Captcha verify
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": RECAPTCHA_SECRET_KEY,
                "response": captcha_token
            }
        )
        if not response.json().get('success'):
            return jsonify({'error': 'Invalid captcha'}), 400

        # Check existing user
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        # Role assign
        role = UserRole.CREATOR if Invitation.query.filter_by(email=email).first() else UserRole.VIEWER
        
        # Generate OTP
        verification_code = str(random.randint(100000, 999999))
        expiry = datetime.utcnow() + timedelta(minutes=10)

        user = User(
            username=username,
            email=email,
            password=password,
            role=role,
            dob=datetime.strptime(dob, "%Y-%m-%d") if dob else None
        )

        user.is_verified = False
        user.verification_code = verification_code
        user.verification_expiry = expiry

        db.session.add(user)
        db.session.commit()

        # SEND EMAIL OTP
        send_verification_email(email, username, verification_code)

        return jsonify({
            "message": "OTP sent successfully",
            "otp_sent": True
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Handles Firebase social login (Google, etc.)
    Uses 'picture' from decoded Firebase token, saves to Cloudflare Images,
    and stores the final URL in user.profile_picture.
    """
    try:
        id_token = request.json.get('idToken')
        if not id_token:
            return jsonify({'error': 'idToken is required'}), 400

        # Verify Firebase token and extract fields
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get('email')
        picture_url = decoded_token.get('picture')  # <-- from your token sample

        if not email:
            return jsonify({'error': 'Email not found in Firebase token'}), 400

        is_new_user = False
        user = User.query.filter_by(email=email).first()
        if not user:
            # Decide role (invited -> CREATOR)
            invitation = Invitation.query.filter_by(email=email).first()
            role = UserRole.CREATOR if invitation else UserRole.VIEWER

            user = User(email=email, role=role)
            db.session.add(user)
            db.session.commit()
            is_new_user = True

        # If user has no profile picture yet and we have a token picture, upload it
        if (not user.profile_picture) and picture_url:
            try:
                # Download the Google picture to a temp file
                resp = requests.get(picture_url, timeout=15)
                resp.raise_for_status()

                # Try to infer a reasonable filename and content-type
                content_type = resp.headers.get('Content-Type', 'image/jpeg')
                ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
                filename = f"profile{ext}"

                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=True) as tmp:
                    tmp.write(resp.content)
                    tmp.flush()

                    # If Cloudflare creds exist, upload; else fallback to Google URL
                    if CLOUDFLARE_API_TOKEN and CLOUDFLARE_IMAGE_URL:
                        headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
                        with open(tmp.name, 'rb') as f:
                            files = {"file": (filename, f, content_type)}
                            cf_res = requests.post(CLOUDFLARE_IMAGE_URL, headers=headers, files=files, timeout=30)

                        if cf_res.status_code == 200:
                            user.profile_picture = cf_res.json()['result']['variants'][0]
                        else:
                            # Fallback to the Google-hosted picture URL
                            user.profile_picture = picture_url
                    else:
                        # No Cloudflare config—just use Google URL
                        user.profile_picture = picture_url

                db.session.commit()

            except Exception as e:
                # If anything goes wrong, do not block login.
                print(f"[login] Profile image processing failed: {e}")
                # As a last fallback, at least store the Google URL if available
                if picture_url and not user.profile_picture:
                    user.profile_picture = picture_url
                    db.session.commit()

        # Issue JWTs for your app
        access_token = create_access_token(identity=user.email)
        refresh_token = create_refresh_token(identity=user.email)
        profile_complete = user.is_profile_complete()

        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(),
            'profile_complete': profile_complete,
            'is_new_user': is_new_user
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"[login] Error in social login: {e}")
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
        bio = request.form.get('bio')
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
            
        user.update_profile(username=username, profile_picture=profile_picture_path, bio=bio)
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
        captcha_token = data.get('recaptchaToken')
        remember_me = data.get("rememberMe", False) 
        
        if not identifier or not password:
            return jsonify({'error': 'Username/email and password are required'}), 400
        
        user = User.query.filter_by(email=identifier).first()
        if not user:
            user = User.query.filter_by(username=identifier).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid username/email or password'}), 400
        
        # BLOCK IF EMAIL NOT VERIFIED
        if not user.is_verified:
            return jsonify({
                "error": "Email not verified",
                "email_not_verified": True,
                "email": user.email
            }), 403
        
        current_ip = request.headers.get("CF-Connecting-IP") or request.remote_addr
        current_user_agent = request.headers.get("User-Agent")

        try:
            geo = requests.get(f"https://ipapi.co/{current_ip}/json/").json()
            current_country = geo.get("country_name", "Unknown")
        except:
            current_country = "Unknown"

        # -------------- SECURITY ALERT CHECK --------------
        from app.utils.email import send_security_alert_email

        def same_subnet(ip1, ip2):
            if not ip1 or not ip2:
                return False
            return ip1.split(".")[:3] == ip2.split(".")[:3]
        is_new_ip = not same_subnet(user.last_login_ip, current_ip)
        is_new_country = (
            current_country != "Unknown" and 
            user.last_login_country and 
            user.last_login_country != current_country
        )
        def extract_browser(ua):
            if not ua:
                return None
            ua = ua.lower()
            if "chrome" in ua:
                return "chrome"
            if "safari" in ua and "chrome" not in ua:
                return "safari"
            if "firefox" in ua:
                return "firefox"
            if "edge" in ua:
                return "edge"
            return "other"
        current_browser = extract_browser(current_user_agent)
        last_browser = extract_browser(user.last_login_user_agent)
        is_new_agent = (
            last_browser 
            and current_browser 
            and last_browser != current_browser
        )
        # Trigger email only if user has previous login info saved
        has_previous_login = (
            user.last_login_ip or 
            user.last_login_country or 
            user.last_login_user_agent
        )
        if has_previous_login and (is_new_ip or is_new_country or is_new_agent):
            send_security_alert_email(
                user.email,
                user.username,
                current_ip,
                current_country
            )
        
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

        # Issue refresh token ONLY if rememberMe = True
        refresh_token = None
        if remember_me:
            refresh_token = create_refresh_token(identity=user.email)
        
        profile_complete = user.is_profile_complete()
        
        user.last_login_ip = current_ip
        user.last_login_country = current_country
        user.last_login_user_agent = current_user_agent
        db.session.commit()
        
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

@auth_bp.route('/creator/<int:creator_id>', methods=['GET'])
def get_creator_by_id(creator_id):
    """Supports public access, but uses token if provided."""
    try:
        creator = User.query.filter_by(id=creator_id, role=UserRole.CREATOR).first()
        if not creator:
            return jsonify({'error': 'Creator not found'}), 404

        is_following_author = False
        try:
            verify_jwt_in_request()    # only works if token exists
            identity = get_jwt_identity()
            if identity:
                current_user = User.query.filter_by(email=identity).first()
                if current_user:
                    is_following_author = current_user.is_following(creator)
        except:
            pass  # no token → treat as guest user

        videos = Video.query.filter_by(created_by=creator.id).all()
        blogs = Blog.query.filter_by(created_by=creator.id).all()

        creator_data = {
            'creator': {
                **creator.to_dict(),
                "is_following_author": is_following_author
            },
            'videos': [v.to_dict() for v in videos],
            'blogs': [b.to_dict() for b in blogs]
        }
        return jsonify(creator_data), 200
    except Exception as e:
        print(f"Error fetching creator: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/blogs/creator/<int:creator_id>', methods=['GET'])
@jwt_required(optional=True)
def get_blogs_by_creator(creator_id):
    """Public: Get published blogs by creator ID"""
    try:
        blogs = Blog.query.filter_by(created_by=creator_id, status=BlogStatus.PUBLISHED).all()
        blogs_data = [
            {
                "id": b.id,
                "title": b.title,
                "excerpt": (b.content[:150] + "...") if b.content else "",
                "views": b.views,
                "likes": b.likes,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in blogs
        ]

        return jsonify({"blogs": blogs_data}), 200
    except Exception as e:
        print("Error in get_blogs_by_creator:", e)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/videos/creator/<int:creator_id>', methods=['GET'])
@jwt_required(optional=True)
def get_videos_by_creator(creator_id):
    """Public: Get published videos by creator ID"""
    try:
        videos = Video.query.filter_by(created_by=creator_id, status=VideoStatus.PUBLISHED).all()

        videos_data = [
            {
                "id": b.id,
                "title": b.title,
                "excerpt": (b.content[:150] + "...") if b.content else "",
                "views": b.views,
                "likes": b.likes,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in videos
        ]

        return jsonify({"videos": videos_data}), 200

    except Exception as e:
        print("Error in get_videos_by_creator:", e)
        return jsonify({"error": "Internal server error"}), 500

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
    
    
@auth_bp.route("/toggle-role", methods=["PATCH"])
@jwt_required()
def toggle_role():
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Creator -> Viewer is always allowed
        if user.role == UserRole.CREATOR:
            user.role = UserRole.VIEWER

        elif user.role == UserRole.VIEWER:
            user.role = UserRole.CREATOR

        else:
            return jsonify({"error": "Role cannot be toggled"}), 400

        db.session.commit()

        return jsonify({
            "message": f"Switched to {user.role.value}",
            "user": user.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Internal server error", "details": str(e)}), 500
    


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        email = request.json.get("email")
        if not email:
            return jsonify({"error": "Email is required"}), 400
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"error": "No user found with this email"}), 404
        token = secrets.token_urlsafe(32)
        print("Generated token:", token)
        print("User before saving:", user.reset_token)

        user.reset_token = token
        user.reset_token_expiry = datetime.utcnow() + timedelta(minutes=30)
        db.session.commit()
        print("User after saving:", user.reset_token)

        reset_url = f"http://116.202.210.102:3001/reset-password?token={token}"
        email_sent = send_reset_password_email(user.email, user.username, reset_url)

        if not email_sent:
            return jsonify({"error": "Failed to send reset email"}), 500
        return jsonify({"message": "Password reset link sent to email"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    try:
        token = request.json.get("token")
        new_password = request.json.get("new_password")

        # decode URL-encoded characters
        decoded_token = unquote(token)
        print("Incoming token:", decoded_token)

        if not decoded_token or not new_password:
            return jsonify({"error": "Token and new password required"}), 400

        user = User.query.filter_by(reset_token=decoded_token).first()
        print("User DB token:", user.reset_token if user else None)

        if not user:
            return jsonify({"error": "Invalid token"}), 400
        if user.reset_token_expiry < datetime.utcnow():
            return jsonify({"error": "Reset link expired"}), 400
        
         # Apply PASSWORD PROTOCOL here
        password_pattern = re.compile(
            r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\'":\\|,.<>\/?])[A-Za-z\d!@#$%^&*()_+\-=\[\]{};\'":\\|,.<>\/?]{8,}$'
        )
        if not password_pattern.match(new_password):
            return jsonify({
                'error': (
                    'Password must be at least 8 characters long and include '
                    'an uppercase letter, lowercase letter, number, and special character.'
                )
            }), 400

        user.password_hash = user._hash_password(new_password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()

        return jsonify({"message": "Password reset successful"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    

@auth_bp.route('/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    try:
        email = get_jwt_identity()
        user = User.query.filter_by(email=email).first()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json()
        current_password = data.get('currentPassword')
        new_password = data.get('newPassword')

        if not current_password or not new_password:
            return jsonify({'error': 'Current and new passwords are required'}), 400

        # Validate current password
        if not user.check_password(current_password):
            return jsonify({'error': 'Incorrect current password'}), 400
        
        password_pattern = re.compile(
            r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\'":\\|,.<>\/?])[A-Za-z\d!@#$%^&*()_+\-=\[\]{};\'":\\|,.<>\/?]{8,}$'
        )
        if not password_pattern.match(new_password):
            return jsonify({
                'error': (
                    'Password must be at least 8 characters long and include '
                    'an uppercase letter, lowercase letter, number, and special character.'
                )
            }), 400

        # Update new password
        user.password_hash = user._hash_password(new_password)
        db.session.commit()

        return jsonify({'message': 'Password changed successfully'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500



@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    try:
        data = request.get_json()
        email = data.get("email")
        code = data.get("code")

        if not email or not code:
            return jsonify({'error': 'Missing fields'}), 400

        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if user.is_verified:
            return jsonify({'message': 'Already verified'}), 200

        if user.verification_code != code:
            return jsonify({'error': 'Invalid OTP'}), 400
        
        if datetime.utcnow() > user.verification_expiry:
            return jsonify({'error': 'OTP expired'}), 400

        user.is_verified = True
        user.verification_code = None
        user.verification_expiry = None
        db.session.commit()

        return jsonify({"message": "Email verified successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    try:
        data = request.get_json()
        email = data.get("email")

        if not email:
            return jsonify({"error": "Email is required"}), 400

        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        if user.is_verified:
            return jsonify({"message": "User already verified"}), 200

        # Generate new OTP
        new_code = str(random.randint(100000, 999999))
        new_expiry = datetime.utcnow() + timedelta(minutes=10)

        user.verification_code = new_code
        user.verification_expiry = new_expiry

        db.session.commit()

        send_verification_email(email, user.username or "User", new_code)

        return jsonify({
            "message": "OTP resent successfully",
            "expires_in_minutes": 10
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500