import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_caching import Cache
from flask_jwt_extended import JWTManager
from config import config
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

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

# Create celery instance at module level
celery_app = Celery('flock_platform')

def make_celery(app):
    celery_app.conf.update(
        broker_url=app.config['REDIS_URL'],
        result_backend=app.config['REDIS_URL'],
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
    )

    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask
    return celery_app

def create_app(config_name='default'):
    """Application factory function"""
    app = Flask(__name__)
    
    from flask import send_from_directory
    import firebase_setup
    
    @app.route('/static/<path:filename>')
    def static_files(filename):
        return send_from_directory(app.static_folder, filename)
    
    # Load configuration
    app.config.from_object(config[config_name])
    app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024

    # Add scheduler & Redis config
    app.config.update({
        'SCHEDULER_API_ENABLED': True,
        'SCHEDULER_TIMEZONE': 'UTC',
        'REDIS_URL': os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    })

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cache.init_app(app)
    CORS(app)

    # Configure celery
    make_celery(app)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.email import email_bp
    from app.routes.blog import blog_bp
    from app.routes.video import video_bp
    from app.routes.content import content_bp
    from app.routes.cpm import cpm_bp
    from app.routes.earnings import earnings_bp
    from app.routes.stripe_webhooks import stripe_webhooks_bp
    from app.routes.paypal import paypal_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(email_bp, url_prefix='/api/email')
    app.register_blueprint(blog_bp, url_prefix='/api/blog')
    app.register_blueprint(video_bp, url_prefix='/api/video')
    app.register_blueprint(content_bp, url_prefix='/api/content')
    app.register_blueprint(cpm_bp, url_prefix='/api/cpm')
    app.register_blueprint(earnings_bp, url_prefix='/api/earnings')
    app.register_blueprint(stripe_webhooks_bp, url_prefix='/api/stripe')
    app.register_blueprint(paypal_bp, url_prefix='/api/paypal')
    
    with app.app_context():
        from app.services import init_scheduler
        init_scheduler(app)
    return app 