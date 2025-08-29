from sqlalchemy import func

from app.models import Blog, Video, BlogStatus, VideoStatus

def get_most_viewed_blogs():
    try:
        most_viewed_blogs = Blog.query.filter(Blog.archived == False, Blog.status == BlogStatus.PUBLISHED).order_by(Blog.views.desc()).limit(10).all()
        return most_viewed_blogs
    except:
        return []

def get_most_viewed_videos():
    try:
        most_viewed_videos = Video.query.filter(Video.archived == False, Video.status == VideoStatus.PUBLISHED).order_by(Video.views.desc()).limit(10).all()
        return most_viewed_videos
    except:
        return []

def get_most_liked_blogs():
    try:
        most_liked_blogs = Blog.query.filter(Blog.archived == False, Blog.status == BlogStatus.PUBLISHED).order_by(Blog.likes.desc()).limit(10).all()
        return most_liked_blogs
    except:
        return []

def get_most_liked_videos():
    try:
        most_liked_videos = Video.query.filter(Video.archived == False, Video.status == VideoStatus.PUBLISHED).order_by(Video.likes.desc()).limit(10).all()
        return most_liked_videos
    except:
        return []
    
def get_random_blogs(creator_id=None):
    try:
        query = Blog.query.filter(Blog.archived == False, Blog.status == BlogStatus.PUBLISHED)
        if creator_id:
            query = query.filter_by(created_by=creator_id)
        random_blogs = query.order_by(func.random()).limit(10).all()
        return random_blogs
    except:
        return []
    
def get_random_videos(creator_id=None):
    try:
        query = Video.query.filter(Video.archived == False, Video.status == VideoStatus.PUBLISHED)
        if creator_id:
            query = query.filter_by(created_by=creator_id)
        random_videos = query.order_by(func.random()).limit(10).all()
        return random_videos
    except:
        return []