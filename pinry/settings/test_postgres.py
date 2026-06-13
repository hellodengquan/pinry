from .base import *

SECRET_KEY = 'test-postgres-key-do-not-use-in-prod'
DEBUG = True
ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'pinry_test'),
        'USER': os.environ.get('POSTGRES_USER', 'pinry'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'pinry'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'TEST': {
            'NAME': os.environ.get('POSTGRES_TEST_DB', 'test_pinry'),
        },
    }
}
