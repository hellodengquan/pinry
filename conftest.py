import sys
import PIL.Image as _PILImage

if not hasattr(_PILImage, 'ANTIALIAS'):
    _PILImage.ANTIALIAS = 2


def pytest_configure(config):
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pinry.settings.development')
    import django
    django.setup()
