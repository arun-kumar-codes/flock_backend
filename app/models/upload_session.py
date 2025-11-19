from app import db

class UploadSession(db.Model):
    __tablename__ = "upload_sessions"

    id = db.Column(db.String(50), primary_key=True)  # Celery task_id
    user_id = db.Column(db.Integer, nullable=False)
    tus_url = db.Column(db.String(500))
    temp_path = db.Column(db.String(500))
    cancelled = db.Column(db.Boolean, default=False)
