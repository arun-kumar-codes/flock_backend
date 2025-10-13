import os
import time
import base64
import tempfile
import requests
from datetime import datetime
from tusclient import client
from app import db, celery_app
from app.models import Video, User
from app.utils import get_video_duration, delete_video_cache
from dotenv import load_dotenv

load_dotenv()

CLOUDFLARE_STREAM_URL = os.getenv("CLOUDFLARE_STREAM_URL")
CLOUDFLARE_IMAGE_URL = os.getenv("CLOUDFLARE_IMAGE_URL")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")


def upload_video_with_tus(file_path, chunk_size=52428800, max_retries=10, timeout=300):
    """Upload video with progress tracking"""

    # Extract filename FIRST
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / (1024 * 1024)

    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Tus-Resumable": "1.0.0",
        "Upload-Metadata": f"name {base64.b64encode(filename.encode()).decode()}"
    }


    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.timeout = timeout

    print(f"⚙️ Using CLOUDFLARE_STREAM_URL: {CLOUDFLARE_STREAM_URL}")

    tus_client = client.TusClient(
        CLOUDFLARE_STREAM_URL,
        headers=headers
    )

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / (1024 * 1024)

    uploader = tus_client.uploader(
        file_path,
        chunk_size=chunk_size,
        metadata={
            'name': filename
        }
    )

    chunk_size_mb = chunk_size / (1024 * 1024)
    print(f"📁 Starting upload: {filename}")
    print(f"📊 File size: {file_size_mb:.2f} MB")
    print(f"📦 Chunk size: {chunk_size_mb:.2f} MB")
    print(f"🔢 Total chunks: ~{file_size // chunk_size}")

    retry_count = 0
    start_time = time.time()
    last_offset = uploader.offset

    while uploader.offset < file_size:
        try:
            chunk_start = time.time()
            uploader.upload_chunk()
            chunk_time = time.time() - chunk_start

            uploaded_mb = uploader.offset / (1024 * 1024)
            percentage = (uploader.offset / file_size) * 100
            chunk_mb = (uploader.offset - last_offset) / (1024 * 1024)
            speed_mbps = chunk_mb / chunk_time if chunk_time > 0 else 0

            print(f"✓ Progress: {uploaded_mb:.1f}/{file_size_mb:.1f} MB "
                  f"({percentage:.1f}%) - Speed: {speed_mbps:.2f} MB/s")

            last_offset = uploader.offset
            retry_count = 0

        except Exception as e:
            retry_count += 1
            if retry_count > max_retries:
                elapsed = time.time() - start_time
                print(f"❌ Upload failed after {max_retries} retries and {elapsed:.0f}s")
                raise Exception(f"Upload failed: {str(e)}")

            wait_time = min(5 * retry_count, 30)
            print(f"⚠️ Upload error at offset {uploader.offset / (1024 * 1024):.1f} MB "
                  f"(attempt {retry_count}/{max_retries}): {str(e)}")
            print(f"⏳ Waiting {wait_time}s before retry...")

            time.sleep(wait_time)
            print(f"🔄 Resuming upload from offset {uploader.offset / (1024 * 1024):.1f} MB")

            uploader = tus_client.uploader(
                file_path,
                chunk_size=chunk_size,
                metadata={'name': filename},
                url=uploader.url
            )
            uploader.offset = last_offset

    elapsed = time.time() - start_time
    print(f"✅ Upload complete in {elapsed:.0f}s!")

    upload_url = uploader.url
    print(f"Upload URL: {upload_url}")

    video_uid = upload_url.split('/')[-1].split('?')[0]
    return video_uid


@celery_app.task(bind=True, name='app.tasks.tasks.upload_video_task')
def upload_video_task(self, user_id, video_data, video_path, thumb_path=None):
    """Background task to upload video and thumbnail to Cloudflare using TUS protocol (no stream ready wait)"""
    try:
        user = User.query.get(user_id)
        if not user:
            raise Exception("User not found")

        # Upload video using TUS
        print(f"Starting TUS upload for video: {video_path}")
        video_uid = upload_video_with_tus(video_path)
        print(f"✓ TUS Upload complete! Video UID: {video_uid}")

        # Fetch actual Cloudflare video details (this gives you playback + thumbnail)
        details_url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/stream/{video_uid}"
        headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}

        details_response = requests.get(details_url, headers=headers)
        if details_response.status_code != 200:
            print(f"⚠️ Failed to fetch Cloudflare details: {details_response.text}")
            details_data = {}
        else:
            details_data = details_response.json().get("result", {})
            print(f"✅ Cloudflare details fetched for UID {video_uid}")

        # Extract URLs dynamically from Cloudflare response
        playback_url = details_data.get("playback", {}).get("hls") or f"https://videodelivery.net/{video_uid}/watch"
        thumbnail_url = details_data.get("thumbnail") or None

        # Optional custom thumbnail upload (to Cloudflare Images)
        if thumb_path:
            try:
                with open(thumb_path, "rb") as f_thumb:
                    thumb_response = requests.post(
                        CLOUDFLARE_IMAGE_URL,
                        headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
                        files={"file": (os.path.basename(thumb_path), f_thumb)}
                    )
                if thumb_response.status_code == 200:
                    thumb_data = thumb_response.json()
                    thumbnail_url = thumb_data["result"]["variants"][0]
                    print(f"✅ Custom thumbnail uploaded successfully: {thumbnail_url}")
                else:
                    print(f"⚠️ Thumbnail upload error: {thumb_response.text}")
            except Exception as thumb_error:
                print(f"❌ Thumbnail upload failed: {str(thumb_error)}")

        # If Cloudflare response or thumbnail upload didn’t provide one, fallback to Stream
        if not thumbnail_url:
            thumbnail_url = f"https://videodelivery.net/{video_uid}/thumbnails/thumbnail.jpg"
            print(f"Using fallback Stream thumbnail: {thumbnail_url}")

        # Duration
        duration = get_video_duration(video_path)

        # Create video record in DB
        video = Video(
            title=video_data["title"],
            description=video_data.get("description"),
            duration=duration,
            video=playback_url,
            thumbnail=thumbnail_url,
            keywords=video_data.get("keywords", []),
            locations=video_data.get("locations", []),
            created_by=user_id,
            is_draft=video_data.get("is_draft", False),
            is_scheduled=video_data.get("is_scheduled", False),
            scheduled_at=video_data.get("scheduled_at"),
            age_restricted=video_data.get("age_restricted", False),
            brand_tags=video_data.get("brand_tags", []),
            paid_promotion=video_data.get("paid_promotion", False),
        )

        db.session.add(video)
        db.session.commit()
        print(f"✅ DB COMMIT VIDEO ID = {video.id}, UID = {video_uid}")

        delete_video_cache()

        # Cleanup temp files
        for f in [video_path, thumb_path]:
            if f and os.path.exists(f):
                os.remove(f)

        print(f"✅ Video committed to DB with UID: {video_uid}")

        return {
            "success": True,
            "message": "Video uploaded and committed successfully",
            "video_uid": video_uid,
            "video_id": video.id,
            "playback_url": playback_url,
            "thumbnail_url": thumbnail_url,
            "duration": duration
        }

    except Exception as e:
        db.session.rollback()
        for f in [video_path, thumb_path]:
            if f and os.path.exists(f):
                os.remove(f)
        print(f"❌ Upload error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Video upload failed. Check Cloudflare logs or retry."
        }
