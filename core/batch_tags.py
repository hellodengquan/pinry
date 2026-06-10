from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from taggit.models import Tag, TaggedItem

from core.models import Pin, Board


def _get_pin_content_type_id():
    return ContentType.objects.get_for_model(Pin).id


class BatchTagResult:
    def __init__(self):
        self.affected_pin_ids = []
        self.skipped_pin_ids = []
        self.skipped_reasons = {}
        self.errors = []

    def to_dict(self):
        return {
            "affected_count": len(self.affected_pin_ids),
            "affected_pin_ids": self.affected_pin_ids,
            "skipped_count": len(self.skipped_pin_ids),
            "skipped_pin_ids": self.skipped_pin_ids,
            "skipped_reasons": self.skipped_reasons,
            "errors": self.errors,
        }


def _normalize_tag_name(name):
    return name.strip().lower()


def _get_all_requested_pins(pin_ids=None, tag_names=None):
    if pin_ids is not None:
        return Pin.objects.filter(id__in=pin_ids)
    elif tag_names is not None:
        return Pin.objects.filter(tags__name__in=tag_names)
    return Pin.objects.none()


def _filter_private_pins(user, pins_qs):
    if user.is_authenticated:
        private_pins = pins_qs.filter(~Q(submitter=user), private=True)
        accessible = pins_qs.exclude(~Q(submitter=user), private=True)
    else:
        private_pins = pins_qs.filter(private=True)
        accessible = pins_qs.exclude(private=True)
    return accessible.distinct(), private_pins.distinct()


def _filter_private_board_pins(user, pins_qs):
    private_boards = Board.objects.filter(private=True)
    if user.is_authenticated:
        private_boards = private_boards.exclude(submitter=user)
    private_board_pin_ids = set()
    for board in private_boards:
        private_board_pin_ids.update(board.pins.values_list("id", flat=True))
    accessible = pins_qs.exclude(id__in=private_board_pin_ids)
    inaccessible = pins_qs.filter(id__in=private_board_pin_ids)
    return accessible, inaccessible


def _resolve_and_filter_pins(user, pin_ids=None, tag_names=None):
    all_pins = _get_all_requested_pins(pin_ids=pin_ids, tag_names=tag_names)
    accessible, private_pins = _filter_private_pins(user, all_pins)
    accessible, board_private_pins = _filter_private_board_pins(user, accessible)

    skipped = {}
    for pid in private_pins.values_list("id", flat=True):
        skipped[pid] = "Pin is private and owned by another user"
    for pid in board_private_pins.values_list("id", flat=True):
        skipped[pid] = "Pin is in a private board you don't own"

    return accessible, skipped


def preview_batch_add(user, pin_ids, tag_names):
    accessible, skipped = _resolve_and_filter_pins(user, pin_ids=pin_ids)

    affected_pin_ids = list(accessible.values_list("id", flat=True))
    skipped_pin_ids = list(skipped.keys())

    tag_conflicts = {}
    normalized_names = {}
    for name in tag_names:
        norm = _normalize_tag_name(name)
        normalized_names[name] = norm
        existing = Tag.objects.filter(name=norm)
        if existing.exists() and norm != name:
            tag_conflicts[name] = {
                "normalized_to": norm,
                "existing_tag": existing.first().name,
                "message": "Tag will be normalized to '{}' (case-insensitive)".format(norm),
            }

    existing_tags = Tag.objects.filter(name__in=[_normalize_tag_name(n) for n in tag_names])
    pins_with_existing = {}
    for tag in existing_tags:
        pin_ids_with_tag = list(
            accessible.filter(tags__name=tag.name).values_list("id", flat=True)
        )
        if pin_ids_with_tag:
            pins_with_existing[tag.name] = pin_ids_with_tag

    return {
        "operation": "add",
        "tags": tag_names,
        "normalized_tags": {k: v for k, v in normalized_names.items() if k != v},
        "tag_conflicts": tag_conflicts,
        "pins_already_having_tag": pins_with_existing,
        "affected_count": len(affected_pin_ids),
        "affected_pin_ids": affected_pin_ids,
        "skipped_count": len(skipped_pin_ids),
        "skipped_pin_ids": skipped_pin_ids,
        "skipped_reasons": {str(k): v for k, v in skipped.items()},
    }


def preview_batch_remove(user, pin_ids, tag_names):
    accessible, skipped = _resolve_and_filter_pins(user, pin_ids=pin_ids)

    affected_pin_ids = list(accessible.values_list("id", flat=True))
    skipped_pin_ids = list(skipped.keys())

    existing_tag_names = set(Tag.objects.filter(name__in=tag_names).values_list("name", flat=True))
    non_existent_tags = [t for t in tag_names if t not in existing_tag_names]

    pins_with_tags = {}
    for tag_name in existing_tag_names:
        pin_ids_with_tag = list(
            accessible.filter(tags__name=tag_name).values_list("id", flat=True)
        )
        if pin_ids_with_tag:
            pins_with_tags[tag_name] = pin_ids_with_tag

    return {
        "operation": "remove",
        "tags": tag_names,
        "non_existent_tags": non_existent_tags,
        "pins_having_tag": pins_with_tags,
        "affected_count": len(affected_pin_ids),
        "affected_pin_ids": affected_pin_ids,
        "skipped_count": len(skipped_pin_ids),
        "skipped_pin_ids": skipped_pin_ids,
        "skipped_reasons": {str(k): v for k, v in skipped.items()},
    }


def preview_batch_merge(user, source_tags, target_tag):
    all_tag_names = list(set(source_tags + [target_tag]))
    accessible, skipped = _resolve_and_filter_pins(user, tag_names=all_tag_names)

    affected_pin_ids = list(accessible.values_list("id", flat=True))
    skipped_pin_ids = list(skipped.keys())

    normalized_target = _normalize_tag_name(target_tag)
    tag_conflicts = {}
    aliases = {}
    for name in source_tags:
        norm = _normalize_tag_name(name)
        if norm != name:
            tag_conflicts[name] = {
                "normalized_to": norm,
                "message": "Source tag will be normalized to '{}'".format(norm),
            }
        existing_variants = Tag.objects.filter(name=norm) | Tag.objects.filter(
            name__iexact=name
        )
        existing_variants = existing_variants.exclude(name=name)
        if existing_variants.exists():
            aliases[name] = [t.name for t in existing_variants.distinct()]

    if _normalize_tag_name(target_tag) != target_tag:
        tag_conflicts[target_tag] = {
            "normalized_to": normalized_target,
            "message": "Target tag will be normalized to '{}'".format(normalized_target),
        }

    source_pin_counts = {}
    for tag_name in source_tags:
        count = accessible.filter(tags__name=tag_name).count()
        if count > 0:
            source_pin_counts[tag_name] = count

    target_pin_count = accessible.filter(tags__name=target_tag).count()

    target_tag_obj = Tag.objects.filter(name=target_tag).first()
    if target_tag_obj and target_tag_obj.name != normalized_target:
        existing_normalized = Tag.objects.filter(name=normalized_target).first()
        if existing_normalized and existing_normalized.id != target_tag_obj.id:
            tag_conflicts[target_tag] = {
                "normalized_to": normalized_target,
                "existing_tag": existing_normalized.name,
                "message": "Target tag '{}' conflicts with existing tag '{}' after normalization".format(
                    target_tag, existing_normalized.name
                ),
            }

    return {
        "operation": "merge",
        "source_tags": source_tags,
        "target_tag": target_tag,
        "normalized_target": normalized_target,
        "tag_conflicts": tag_conflicts,
        "aliases": aliases,
        "source_pin_counts": source_pin_counts,
        "target_pin_count": target_pin_count,
        "affected_count": len(affected_pin_ids),
        "affected_pin_ids": affected_pin_ids,
        "skipped_count": len(skipped_pin_ids),
        "skipped_pin_ids": skipped_pin_ids,
        "skipped_reasons": {str(k): v for k, v in skipped.items()},
    }


def execute_batch_add(user, pin_ids, tag_names, dry_run=False):
    result = BatchTagResult()
    accessible, skipped = _resolve_and_filter_pins(user, pin_ids=pin_ids)

    result.skipped_pin_ids = list(skipped.keys())
    result.skipped_reasons = {str(k): v for k, v in skipped.items()}

    if dry_run:
        result.affected_pin_ids = list(accessible.values_list("id", flat=True))
        return result

    normalized_tags = []
    for name in tag_names:
        norm = _normalize_tag_name(name)
        tag, _ = Tag.objects.get_or_create(
            defaults={"name": norm, "slug": norm},
            name=norm,
        )
        normalized_tags.append(tag)

    content_type_id = _get_pin_content_type_id()

    with transaction.atomic():
        for pin in accessible:
            try:
                with transaction.atomic():
                    for tag in normalized_tags:
                        TaggedItem.objects.get_or_create(
                            tag=tag,
                            content_type_id=content_type_id,
                            object_id=pin.id,
                            defaults={},
                        )
                    result.affected_pin_ids.append(pin.id)
            except Exception as e:
                result.errors.append({"pin_id": pin.id, "error": str(e)})

    return result


def execute_batch_remove(user, pin_ids, tag_names, dry_run=False):
    result = BatchTagResult()
    accessible, skipped = _resolve_and_filter_pins(user, pin_ids=pin_ids)

    result.skipped_pin_ids = list(skipped.keys())
    result.skipped_reasons = {str(k): v for k, v in skipped.items()}

    if dry_run:
        result.affected_pin_ids = list(accessible.values_list("id", flat=True))
        return result

    existing_tags = Tag.objects.filter(name__in=tag_names)
    if not existing_tags.exists():
        result.errors.append({"error": "None of the specified tags exist"})
        return result

    tag_ids = list(existing_tags.values_list("id", flat=True))
    content_type_id = _get_pin_content_type_id()

    with transaction.atomic():
        for pin in accessible:
            try:
                with transaction.atomic():
                    deleted_count, _ = TaggedItem.objects.filter(
                        tag_id__in=tag_ids,
                        content_type_id=content_type_id,
                        object_id=pin.id,
                    ).delete()
                    if deleted_count > 0:
                        result.affected_pin_ids.append(pin.id)
            except Exception as e:
                result.errors.append({"pin_id": pin.id, "error": str(e)})

    _cleanup_orphan_tags(tag_ids)

    return result


def execute_batch_merge(user, source_tags, target_tag, dry_run=False):
    result = BatchTagResult()
    normalized_target = _normalize_tag_name(target_tag)

    target_tag_obj, _ = Tag.objects.get_or_create(
        defaults={"name": normalized_target, "slug": normalized_target},
        name=normalized_target,
    )

    all_tag_names = list(set(source_tags))
    source_tag_objs = Tag.objects.filter(name__in=all_tag_names)
    source_tag_ids = list(source_tag_objs.values_list("id", flat=True))

    accessible, skipped = _resolve_and_filter_pins(
        user, tag_names=all_tag_names + [normalized_target]
    )

    result.skipped_pin_ids = list(skipped.keys())
    result.skipped_reasons = {str(k): v for k, v in skipped.items()}

    if dry_run:
        result.affected_pin_ids = list(accessible.values_list("id", flat=True))
        return result

    content_type_id = _get_pin_content_type_id()

    with transaction.atomic():
        for pin in accessible:
            try:
                with transaction.atomic():
                    has_target = TaggedItem.objects.filter(
                        tag=target_tag_obj,
                        content_type_id=content_type_id,
                        object_id=pin.id,
                    ).exists()

                    TaggedItem.objects.filter(
                        tag_id__in=source_tag_ids,
                        content_type_id=content_type_id,
                        object_id=pin.id,
                    ).delete()

                    if not has_target:
                        TaggedItem.objects.get_or_create(
                            tag=target_tag_obj,
                            content_type_id=content_type_id,
                            object_id=pin.id,
                            defaults={},
                        )

                    result.affected_pin_ids.append(pin.id)
            except Exception as e:
                result.errors.append({"pin_id": pin.id, "error": str(e)})

    _cleanup_orphan_tags(source_tag_ids)

    return result


def _cleanup_orphan_tags(tag_ids):
    for tag_id in tag_ids:
        if not TaggedItem.objects.filter(tag_id=tag_id).exists():
            Tag.objects.filter(id=tag_id).delete()
