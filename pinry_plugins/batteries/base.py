from abc import ABC
from typing import Any, Dict, Optional

from core.models import Image
from core.services.preview_service import (
    PreviewError,
    PreviewRequest,
    PreviewResult,
)
from django_images.models import Thumbnail


class PinryBasePlugin(ABC):
    name: str = ""
    version: str = "0.1.0"
    description: str = ""

    def __init__(self) -> None:
        if not self.name:
            self.name = type(self).__name__

    def process_image_pre_creation(
        self,
        django_settings: Any,
        image_instance: Image,
    ) -> None:
        pass

    def process_thumbnail_pre_creation(
        self,
        django_settings: Any,
        thumbnail_instance: Thumbnail,
    ) -> None:
        pass

    def preview_pre_fetch(
        self,
        django_settings: Any,
        preview_request: PreviewRequest,
    ) -> None:
        pass

    def preview_post_fetch(
        self,
        django_settings: Any,
        preview_request: PreviewRequest,
        preview_result: PreviewResult,
    ) -> Optional[Dict[str, Any]]:
        return None

    def preview_on_error(
        self,
        django_settings: Any,
        preview_request: PreviewRequest,
        preview_error: PreviewError,
    ) -> None:
        pass
