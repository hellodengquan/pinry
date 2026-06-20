from typing import Any, Dict, Optional

from core.models import Image
from core.services.preview_service import PreviewError, PreviewRequest, PreviewResult
from django_images.models import Thumbnail


class Plugin:
    def process_image_pre_creation(self, django_settings, image_instance: Image):
        pass

    def process_thumbnail_pre_creation(self, django_settings, thumbnail_instance: Thumbnail):
        pass

    def preview_pre_fetch(
        self,
        django_settings,
        preview_request: PreviewRequest,
    ) -> None:
        pass

    def preview_post_fetch(
        self,
        django_settings,
        preview_request: PreviewRequest,
        preview_result: PreviewResult,
    ) -> Optional[Dict[str, Any]]:
        return None

    def preview_on_error(
        self,
        django_settings,
        preview_request: PreviewRequest,
        preview_error: PreviewError,
    ) -> None:
        pass
