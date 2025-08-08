from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.utils import get_most_viewed_blogs, get_most_viewed_videos, get_most_liked_blogs, get_most_liked_videos
from app.models import User
from app import cache

content_bp = Blueprint('content', __name__)

@content_bp.route('/most-viewed', methods=['GET'])
@jwt_required()
@cache.cached(timeout=300, key_prefix=lambda: f"get_most_viewed_content:{request.full_path}")
def get_most_viewed_content():
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()
    most_viewed_blogs = get_most_viewed_blogs()
    most_viewed_blogs = [blog.to_dict(user.id if user else None) for blog in most_viewed_blogs]
    most_viewed_videos = get_most_viewed_videos()
    most_viewed_videos = [video.to_dict(user.id if user else None) for video in most_viewed_videos]
    return jsonify({'blogs': most_viewed_blogs, 'videos': most_viewed_videos}), 200

@content_bp.route('/most-liked', methods=['GET'])
@jwt_required()
@cache.cached(timeout=300, key_prefix=lambda: f"get_most_liked_content:{request.full_path}")
def get_most_liked_content():
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()
    most_liked_blogs = get_most_liked_blogs()
    most_liked_blogs = [blog.to_dict(user.id if user else None) for blog in most_liked_blogs]
    most_liked_videos = get_most_liked_videos()
    most_liked_videos = [video.to_dict(user.id if user else None) for video in most_liked_videos]
    return jsonify({'blogs': most_liked_blogs, 'videos': most_liked_videos}), 200