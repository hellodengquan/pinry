from pinry_plugins.events import Event, EventType


class Plugin:
    def handle_event(self, event: Event):
        event_type = event.type
        if event_type == EventType.PIN_PRE_CREATE:
            self.process_pin_pre_create(event)
        elif event_type == EventType.PIN_POST_CREATE:
            self.process_pin_post_create(event)
        elif event_type == EventType.PIN_PRE_UPDATE:
            self.process_pin_pre_update(event)
        elif event_type == EventType.PIN_POST_UPDATE:
            self.process_pin_post_update(event)
        elif event_type == EventType.PIN_PRE_DELETE:
            self.process_pin_pre_delete(event)
        elif event_type == EventType.PIN_POST_DELETE:
            self.process_pin_post_delete(event)
        elif event_type == EventType.PIN_SYNC:
            self.process_pin_sync(event)
        elif event_type == EventType.IMAGE_PRE_CREATE:
            self.process_image_pre_create(event)
        elif event_type == EventType.IMAGE_POST_CREATE:
            self.process_image_post_create(event)
        elif event_type == EventType.IMAGE_PRE_DELETE:
            self.process_image_pre_delete(event)
        elif event_type == EventType.IMAGE_POST_DELETE:
            self.process_image_post_delete(event)
        elif event_type == EventType.THUMBNAIL_PRE_CREATE:
            self.process_thumbnail_pre_create(event)
        elif event_type == EventType.THUMBNAIL_POST_CREATE:
            self.process_thumbnail_post_create(event)
        elif event_type == EventType.BOARD_PRE_CREATE:
            self.process_board_pre_create(event)
        elif event_type == EventType.BOARD_POST_CREATE:
            self.process_board_post_create(event)
        elif event_type == EventType.BOARD_PRE_UPDATE:
            self.process_board_pre_update(event)
        elif event_type == EventType.BOARD_POST_UPDATE:
            self.process_board_post_update(event)
        elif event_type == EventType.BOARD_PRE_DELETE:
            self.process_board_pre_delete(event)
        elif event_type == EventType.BOARD_POST_DELETE:
            self.process_board_post_delete(event)
        elif event_type == EventType.FETCH_PREVIEW_START:
            self.process_fetch_preview_start(event)
        elif event_type == EventType.FETCH_PREVIEW_SUCCESS:
            self.process_fetch_preview_success(event)
        elif event_type == EventType.FETCH_PREVIEW_FAILURE:
            self.process_fetch_preview_failure(event)

    def process_pin_pre_create(self, event: Event):
        pass

    def process_pin_post_create(self, event: Event):
        pass

    def process_pin_pre_update(self, event: Event):
        pass

    def process_pin_post_update(self, event: Event):
        pass

    def process_pin_pre_delete(self, event: Event):
        pass

    def process_pin_post_delete(self, event: Event):
        pass

    def process_pin_sync(self, event: Event):
        pass

    def process_image_pre_create(self, event: Event):
        pass

    def process_image_post_create(self, event: Event):
        pass

    def process_image_pre_delete(self, event: Event):
        pass

    def process_image_post_delete(self, event: Event):
        pass

    def process_thumbnail_pre_create(self, event: Event):
        pass

    def process_thumbnail_post_create(self, event: Event):
        pass

    def process_board_pre_create(self, event: Event):
        pass

    def process_board_post_create(self, event: Event):
        pass

    def process_board_pre_update(self, event: Event):
        pass

    def process_board_post_update(self, event: Event):
        pass

    def process_board_pre_delete(self, event: Event):
        pass

    def process_board_post_delete(self, event: Event):
        pass

    def process_fetch_preview_start(self, event: Event):
        pass

    def process_fetch_preview_success(self, event: Event):
        pass

    def process_fetch_preview_failure(self, event: Event):
        pass
