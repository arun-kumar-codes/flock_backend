from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import config

from dotenv import load_dotenv
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()

def create_app(config_name='default'):
    """Application factory function"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    CORS(app)
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.email import email_bp
    from app.routes.blog import blog_bp
    from app.routes.video import video_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(email_bp, url_prefix='/api/email')
    app.register_blueprint(blog_bp, url_prefix='/api/blog')
    app.register_blueprint(video_bp, url_prefix='/api/video')
    
    return app 