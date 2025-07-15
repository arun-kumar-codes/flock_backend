"""Create admin user

Revision ID: 0c5c198ddd38
Revises: 6cf8808a562c
Create Date: 2025-07-14 09:42:21.726047

"""
from alembic import op
import sqlalchemy as sa
import bcrypt
import os


# revision identifiers, used by Alembic.
revision = '0c5c198ddd38'
down_revision = '6cf8808a562c'
branch_labels = None
depends_on = None


def upgrade():
    """Create admin user with configurable credentials"""
    # Get connection
    connection = op.get_bind()
    
    # Get admin credentials from environment variables or use defaults
    admin_username = os.getenv('ADMIN_USERNAME', 'admin')
    admin_email = os.getenv('ADMIN_EMAIL', 'admin@admin.com')
    admin_password = os.getenv('ADMIN_PASSWORD', 'Admin@123')
    
    # Hash the admin password
    password_hash = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Check if admin user already exists
    existing_user = connection.execute(sa.text("""
        SELECT id FROM users WHERE username = :username
    """), {'username': admin_username}).fetchone()
    
    if existing_user:
        print(f"Admin user '{admin_username}' already exists, skipping...")
        return
    
    # Insert admin user
    connection.execute(sa.text("""
        INSERT INTO users (username, email, password_hash, role)
        VALUES (:username, :email, :password_hash, :role)
    """), {
        'username': admin_username,
        'email': admin_email,
        'password_hash': password_hash,
        'role': 'ADMIN',
    })
    
    print(f"Admin user '{admin_username}' created successfully!")


def downgrade():
    """Remove admin user"""
    # Get connection
    connection = op.get_bind()
    
    # Get admin username from environment or use default
    admin_username = os.getenv('ADMIN_USERNAME', 'admin')
    
    # Delete admin user
    connection.execute(sa.text("""
        DELETE FROM users WHERE username = :username
    """), {'username': admin_username})
    
    print(f"Admin user '{admin_username}' removed successfully!") 
