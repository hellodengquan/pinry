from django.urls import path, include, re_path

from users.views import login_user
from . import views


app_name = "users"
urlpatterns = [
    path('', include(views.drf_router.urls)),
    path('login/', login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),
]
