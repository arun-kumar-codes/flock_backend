import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_caching import Cache
from flask_jwt_extended import JWTManager
from config import config

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()

cache_config = {
    'CACHE_TYPE': 'RedisCache',
    'CACHE_REDIS_URL': os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    'CACHE_KEY_PREFIX': 'flock_platform_'
}
cache = Cache(config=cache_config)

def create_app(config_name='default'):
    """Application factory function"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Add scheduler configuration
    app.config.update({
        'SCHEDULER_API_ENABLED': True,
        'SCHEDULER_TIMEZONE': 'UTC',
        })
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cache.init_app(app)
    CORS(app)
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.email import email_bp
    from app.routes.blog import blog_bp
    from app.routes.video import video_bp
    from app.routes.content import content_bp
    from app.routes.cpm import cpm_bp
    from app.routes.earnings import earnings_bp
    from app.routes.stripe_webhooks import stripe_webhooks_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(email_bp, url_prefix='/api/email')
    app.register_blueprint(blog_bp, url_prefix='/api/blog')
    app.register_blueprint(video_bp, url_prefix='/api/video')
    app.register_blueprint(content_bp, url_prefix='/api/content')
    app.register_blueprint(cpm_bp, url_prefix='/api/cpm')
    app.register_blueprint(earnings_bp, url_prefix='/api/earnings')
    app.register_blueprint(stripe_webhooks_bp, url_prefix='/api/stripe')
    
    with app.app_context():
        from app.services import init_scheduler
        init_scheduler(app)
    return app 