from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin


class Public(MiddlewareMixin):

    acceptable_paths = (
        "/api/v2/profile/",
    )

    def process_request(self, request):
        if settings.PUBLIC is False and not request.user.is_authenticated:
            for path in self.acceptable_paths:
                if not request.path.startswith(path):
                    return HttpResponseForbidden()


class UserLocaleMiddleware(MiddlewareMixin):
    """优先使用用户保存的系统语言，其次使用浏览器语言。

    优先级：
    1. URL/显式切换（如 `lang` query param）——保留 Django LocaleMiddleware 的现有能力（若有）
    2. 用户 UserSettings.language（已登录）
    3. Accept-Language header（浏览器）
    4. settings.LANGUAGE_CODE
    """

    def process_request(self, request):
        if request.user.is_authenticated:
            try:
                lang = request.user.settings.language
            except Exception:
                lang = None
            if lang:
                translation.activate(lang)
                request.LANGUAGE_CODE = translation.get_language()
