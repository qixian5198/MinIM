import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://minim:minim_dev@localhost:5432/minim")
os.environ.setdefault("JWT_SECRET", "test-secret")
