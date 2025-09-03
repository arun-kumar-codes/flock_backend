from flask_apscheduler import APScheduler
from datetime import datetime

# Create global scheduler instance
scheduler = APScheduler()

def init_scheduler(app):
    """Initialize the scheduler with Flask app"""
    scheduler.init_app(app)
    scheduler.start()
    
    scheduler.add_job(
        id='publish_scheduled_content',
        func=lambda: publish_scheduled_content_with_context(app),
        trigger='interval',
        minutes=10,
        replace_existing=True
    )
    
    print("Flask-APScheduler started successfully")

def publish_scheduled_content_with_context(app):
    """Publish scheduled content with proper app context"""
    with app.app_context():
        publish_scheduled_content(app)

def publish_scheduled_content(app):
    """Publish scheduled content - runs every minute"""
    try:
        from app import db
        from app.models import Blog, Video
        
        current_time = datetime.utcnow()
        
        # Find blogs that are scheduled and ready to publish
        scheduled_blogs = Blog.query.filter(
            Blog.is_scheduled == True,
            Blog.scheduled_at <= current_time
        ).all()
        print(scheduled_blogs)
        
        for blog in scheduled_blogs:
            if blog.publish_scheduled():
                print(f"Published scheduled blog: {blog.title}")
                
        scheduled_videos = Video.query.filter(
            Video.is_scheduled == True,
            Video.scheduled_at <= current_time
        ).all()
        print(scheduled_videos)
        
        for video in scheduled_videos:
            if video.publish_scheduled():
                print(f"Published scheduled video: {video.title}")
        
        # Commit all changes
        if scheduled_blogs or scheduled_videos:
            db.session.commit()
            print(f"Published {len(scheduled_blogs)} scheduled blogs and {len(scheduled_videos)} scheduled videos")
    except Exception as e:
        print(f"Error in publish_scheduled_content: {e}")
        try:
            db.session.rollback()
        except:
            pass