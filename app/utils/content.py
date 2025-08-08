from app.models import Blog, Video, BlogStatus, VideoStatus

def get_most_viewed_blogs():
    try:
        most_viewed_blogs = Blog.query.filter(Blog.archived == False, Blog.status == BlogStatus.PUBLISHED).order_by(Blog.views.desc()).limit(10).all()
        return most_viewed_blogs
    except Exception as e:
        print(f"Error getting most viewed blogs: {e}")
        return []

def get_most_viewed_videos():
    try:
        most_viewed_videos = Video.query.filter(Video.archived == False, Video.status == VideoStatus.PUBLISHED).order_by(Video.views.desc()).limit(10).all()
        return most_viewed_videos
    except Exception as e:
        print(f"Error getting most viewed videos: {e}")
        return []

def get_most_liked_blogs():
    try:
        most_liked_blogs = Blog.query.filter(Blog.archived == False, Blog.status == BlogStatus.PUBLISHED).order_by(Blog.likes.desc()).limit(10).all()
        return most_liked_blogs
    except Exception as e:
        print(f"Error getting most liked blogs: {e}")
        return []

def get_most_liked_videos():
    try:
        most_liked_videos = Video.query.filter(Video.archived == False, Video.status == VideoStatus.PUBLISHED).order_by(Video.likes.desc()).limit(10).all()
        return most_liked_videos
    except Exception as e:
        print(f"Error getting most liked videos: {e}")
        return []