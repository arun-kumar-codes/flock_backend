import subprocess
from datetime import datetime, timedelta

from flask import jsonify

from app import cache
from app.models import Video, VideoStatus

def get_video_duration(file_path):
    """Extract video duration using ffprobe"""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'quiet', 
            '-show_entries', 'format=duration', 
            '-of', 'csv=p=0', 
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        return int(duration)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None
    
def transcode_video(file_path, transcoded_path):
    try:
        subprocess.run([
                        "ffmpeg", "-i", file_path,
                        "-c:v", "libx264", "-preset", "fast",
                        "-c:a", "aac", "-b:a", "128k",
                        "-movflags", "+faststart",
                        transcoded_path
                    ], check=True)
    except subprocess.CalledProcessError:
        return jsonify({'error': 'Video transcoding failed'}), 400
    
def get_trending_videos():
    try:
        trending_videos = Video.query.filter(
            Video.archived == False,
            Video.status == VideoStatus.PUBLISHED,
            # Video.created_at > datetime.utcnow() - timedelta(days=7),
            Video.views >= 1,
            Video.likes >= 1
        ).order_by(Video.views.desc()).limit(10).all()
        return trending_videos
    except:
        return []
    
def delete_video_cache():
    redis_client = cache.cache._write_client
    for key in redis_client.scan_iter("flock_platform_content*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("flock_platform_get_all_videos*"):
        redis_client.delete(key)