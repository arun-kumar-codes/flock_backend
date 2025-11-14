import os
from datetime import timedelta

from dotenv import load_dotenv
load_dotenv()

class Config:
    """Base configuration class"""
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', '')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Stripe Configuration
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
    STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_WEBHOOK_ACCOUNT_SECRET = os.getenv('STRIPE_WEBHOOK_ACCOUNT_SECRET', '')
    STRIPE_WEBHOOK_CONNECT_SECRET = os.getenv('STRIPE_WEBHOOK_CONNECT_SECRET', '')
    STRIPE_CONNECT_CLIENT_ID = os.getenv('STRIPE_CONNECT_CLIENT_ID', '')
    
    # Paypal Configuration
    PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID', '')
    PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET', '')
    PAYPAL_SANDBOX = os.getenv('PAYPAL_SANDBOX_NEW', 'true').lower() == 'true'
    PAYPAL_REDIRECT_URI = os.getenv('PAYPAL_REDIRECT_URI', '')
    FRONTEND_SUCCESS_URL = os.getenv('FRONTEND_SUCCESS_URL', '')
    FRONTEND_ERROR_URL = os.getenv('FRONTEND_ERROR_URL', '')

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DEV_DATABASE_URL', 
        'postgresql://postgres:password@localhost/flock_platform_dev')

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv('TEST_DATABASE_URL', 
        'postgresql://postgres:password@localhost/flock_platform_test')

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 
        'postgresql://postgres:password@localhost/flock_platform')

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 