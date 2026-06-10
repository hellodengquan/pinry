from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core.views import drf_router

router = DefaultRouter()
router.registry.extend(drf_router.registry)

urlpatterns = [
    path('api/v2/', include(router.urls)),
    path('users/', include('users.urls')),
]
