from .development import *

ROOT_URLCONF = 'pinry.urls_test'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
