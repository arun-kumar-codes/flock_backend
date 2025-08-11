import requests
import os
from datetime import datetime, timedelta
from app import cache
from app.models import Blog, BlogStatus

CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_IMAGE_URL = os.getenv('CLOUDFLARE_IMAGE_URL')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    """Check if the file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
           
def delete_previous_image(image_url):
    try:
        parts = image_url.strip().split("/")
        image_id = parts[-2]
        url = f"{CLOUDFLARE_IMAGE_URL}/{image_id}"
        headers = {
            "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
        }
        response = requests.delete(url, headers=headers)
    except Exception:
        pass
    
def get_trending_blogs():
    try:
        trending_blogs = Blog.query.filter(
            Blog.archived == False,
            Blog.status == BlogStatus.PUBLISHED,
            Blog.created_at > datetime.utcnow() - timedelta(days=7),
            Blog.views >= 1,
            Blog.likes >= 1
        ).order_by(Blog.views.desc()).limit(10).all()
        return trending_blogs
    except Exception as e:
        print(f"Error getting trending blogs: {e}")
        return []
    
def delete_blog_cache():
    redis_client = cache.cache._write_client
    for key in redis_client.scan_iter("get_all_blogs:*"):
        redis_client.delete(key)