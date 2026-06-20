try:
    from django.urls import re_path as url
except ImportError:
    from django.conf.urls import url
from django.urls import include

from users.views import login_user
from . import views


app_name = "users"
urlpatterns = [
    url(r'', include(views.drf_router.urls)),
    url(r'^login/$', login_user, name='login'),
    url(r'^logout/$', views.logout_user, name='logout'),
]
