import hashlib
import os
import json
import datetime

from django.conf import settings


DEFAULT_EXCLUDE_DIRS = {'.git', '.svn', '.hg', '.DS_Store', '__pycache__', 'node_modules', 'tmp', 'temp'}
DEFAULT_MAX_DEPTH = 10
DEFAULT_AUDIT_LOG_RETENTION_DAYS = 90


def _get_setting(name, default):
    return getattr(settings, name, default)


def get_exclude_dirs():
    config_exclude = _get_setting('MEDIA_CHECK_EXCLUDE_DIRS', None)
    if config_exclude is None:
        return set(DEFAULT_EXCLUDE_DIRS)
    return set(DEFAULT_EXCLUDE_DIRS) | set(config_exclude)


def get_max_depth():
    return _get_setting('MEDIA_CHECK_MAX_DEPTH', DEFAULT_MAX_DEPTH)


def get_audit_log_retention_days():
    return _get_setting('MEDIA_CHECK_AUDIT_RETENTION_DAYS', DEFAULT_AUDIT_LOG_RETENTION_DAYS)


def upload_path(instance, filename, **kwargs):
    hasher = hashlib.md5()
    for chunk in instance.image.chunks():
        hasher.update(chunk)
    hash = hasher.hexdigest()
    base, ext = os.path.splitext(filename)
    return '%(first)s/%(second)s/%(hash)s/%(base)s%(ext)s' % {
        'first': hash[0],
        'second': hash[1],
        'hash': hash,
        'base': base,
        'ext': ext,
    }


def get_all_media_files(max_depth=None, exclude_dirs=None):
    if max_depth is None:
        max_depth = get_max_depth()

    effective_exclude_dirs = get_exclude_dirs()
    if exclude_dirs is not None:
        effective_exclude_dirs = effective_exclude_dirs | set(exclude_dirs)

    media_root = settings.MEDIA_ROOT
    all_files = set()
    if not os.path.exists(media_root):
        return all_files

    base_depth = media_root.rstrip(os.sep).count(os.sep)

    for root, dirs, files in os.walk(media_root):
        current_depth = root.count(os.sep) - base_depth

        dirs[:] = [d for d in dirs if d not in effective_exclude_dirs and not d.startswith('.')]

        if max_depth is not None and current_depth >= max_depth:
            dirs[:] = []

        for file in files:
            if file.startswith('.'):
                continue
            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, media_root)
            all_files.add(relative_path)

    return all_files


def get_all_db_images():
    from django_images.models import Image, Thumbnail

    db_files = set()
    for image in Image.objects.all():
        if image.image.name:
            db_files.add(image.image.name)
    for thumbnail in Thumbnail.objects.all():
        if thumbnail.image.name:
            db_files.add(thumbnail.image.name)
    return db_files


def check_pins_without_valid_image():
    from core.models import Pin

    pins_without_image = []
    for pin in Pin.objects.select_related('image'):
        if not pin.image or not pin.image.image.name:
            pins_without_image.append({
                'id': pin.id,
                'submitter': pin.submitter.username,
                'description': pin.description[:50] if pin.description else '',
            })
    return pins_without_image


def get_orphan_files(max_depth=None, exclude_dirs=None):
    all_media_files = get_all_media_files(max_depth=max_depth, exclude_dirs=exclude_dirs)
    all_db_files = get_all_db_images()
    return all_media_files - all_db_files


def get_missing_files(max_depth=None, exclude_dirs=None):
    all_media_files = get_all_media_files(max_depth=max_depth, exclude_dirs=exclude_dirs)
    all_db_files = get_all_db_images()
    return all_db_files - all_media_files


def run_media_check(max_depth=None, exclude_dirs=None):
    if max_depth is None:
        max_depth = get_max_depth()

    effective_exclude_dirs = get_exclude_dirs()
    if exclude_dirs is not None:
        effective_exclude_dirs = effective_exclude_dirs | set(exclude_dirs)

    media_root = settings.MEDIA_ROOT
    all_media_files = get_all_media_files(max_depth=max_depth, exclude_dirs=exclude_dirs)
    all_db_files = get_all_db_images()
    orphan_files = get_orphan_files(max_depth=max_depth, exclude_dirs=exclude_dirs)
    missing_files = get_missing_files(max_depth=max_depth, exclude_dirs=exclude_dirs)
    pins_without_image = check_pins_without_valid_image()

    orphan_files_with_size = []
    for file in sorted(orphan_files):
        full_path = os.path.join(media_root, file)
        size = os.path.getsize(full_path) if os.path.exists(full_path) else 0
        orphan_files_with_size.append({
            'path': file,
            'size': size,
        })

    return {
        'media_root': media_root,
        'scan_time': datetime.datetime.now().isoformat(),
        'max_depth': max_depth,
        'exclude_dirs': sorted(list(effective_exclude_dirs)),
        'total_files': len(all_media_files),
        'total_db_files': len(all_db_files),
        'orphan_count': len(orphan_files),
        'missing_count': len(missing_files),
        'orphan_files': orphan_files_with_size,
        'missing_files': sorted(list(missing_files)),
        'pins_without_image': pins_without_image,
    }


def save_report(report, output_path):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return output_path


def delete_orphan_files(max_depth=None, exclude_dirs=None):
    orphan_files = get_orphan_files(max_depth=max_depth, exclude_dirs=exclude_dirs)
    media_root = settings.MEDIA_ROOT
    deleted = []
    errors = []

    for file in orphan_files:
        full_path = os.path.join(media_root, file)
        try:
            os.remove(full_path)
            deleted.append(file)
        except OSError as e:
            errors.append({
                'path': file,
                'error': str(e),
            })

    return {
        'deleted_count': len(deleted),
        'deleted_files': deleted,
        'errors': errors,
    }


def fix_missing_files(max_depth=None, exclude_dirs=None):
    from django_images.models import Image, Thumbnail
    from core.models import Pin

    missing_files = get_missing_files(max_depth=max_depth, exclude_dirs=exclude_dirs)
    fixed_images = 0
    fixed_thumbnails = 0
    fixed_pins = 0
    errors = []

    for file in missing_files:
        image = Image.objects.filter(image=file).first()
        if image:
            try:
                pins = Pin.objects.filter(image=image)
                fixed_pins += pins.count()
                pins.delete()
                image.delete()
                fixed_images += 1
            except Exception as e:
                errors.append({
                    'path': file,
                    'type': 'Image',
                    'error': str(e),
                })
            continue

        thumbnail = Thumbnail.objects.filter(image=file).first()
        if thumbnail:
            try:
                thumbnail.delete()
                fixed_thumbnails += 1
            except Exception as e:
                errors.append({
                    'path': file,
                    'type': 'Thumbnail',
                    'error': str(e),
                })

    return {
        'fixed_images': fixed_images,
        'fixed_thumbnails': fixed_thumbnails,
        'fixed_pins': fixed_pins,
        'errors': errors,
    }


class MediaCheckRenderer:
    def __init__(self, report, orphan_result=None, missing_result=None):
        self.report = report
        self.orphan_result = orphan_result
        self.missing_result = missing_result

    def _get_summary_fields(self):
        return [
            ('media_root', '媒体根目录', self.report.get('media_root', '')),
            ('scan_time', '扫描时间', self.report.get('scan_time', '')),
            ('max_depth', '最大扫描深度', str(self.report.get('max_depth', ''))),
            ('exclude_dirs', '排除目录', ', '.join(self.report.get('exclude_dirs', []))),
            ('total_files', '文件系统中的文件总数', str(self.report.get('total_files', 0))),
            ('total_db_files', '数据库中的文件总数', str(self.report.get('total_db_files', 0))),
            ('orphan_count', '孤儿文件数量', str(self.report.get('orphan_count', 0))),
            ('missing_count', '缺失文件数量', str(self.report.get('missing_count', 0))),
        ]

    def to_json(self):
        result = dict(self.report)
        if self.orphan_result is not None:
            result['delete_orphans_result'] = self.orphan_result
        if self.missing_result is not None:
            result['fix_missing_result'] = self.missing_result
        return json.dumps(result, ensure_ascii=False, indent=2)

    def to_dict(self):
        result = dict(self.report)
        if self.orphan_result is not None:
            result['delete_orphans_result'] = self.orphan_result
        if self.missing_result is not None:
            result['fix_missing_result'] = self.missing_result
        return result

    def to_text(self, quiet=False):
        lines = []

        for key, label, value in self._get_summary_fields():
            lines.append(f'{label}: {value}')

        lines.append('')
        lines.append('=== 巡检结果 ===')
        lines.append(f'文件系统中的文件总数: {self.report.get("total_files", 0)}')
        lines.append(f'数据库中的文件总数: {self.report.get("total_db_files", 0)}')
        lines.append(f'孤儿文件数量: {self.report.get("orphan_count", 0)}')
        lines.append(f'缺失文件数量: {self.report.get("missing_count", 0)}')
        lines.append('')

        if not quiet and self.report.get('orphan_files'):
            lines.append('=== 孤儿文件列表 ===')
            for file_info in self.report['orphan_files']:
                lines.append(f'  - {file_info["path"]} ({file_info["size"]} bytes)')
            lines.append('')

        if not quiet and self.report.get('missing_files'):
            lines.append('=== 缺失文件列表 ===')
            for file in self.report['missing_files']:
                lines.append(f'  - {file}')
            lines.append('')

        pins = self.report.get('pins_without_image', [])
        if pins:
            lines.append(f'=== 缺少图片的Pin ({len(pins)} 个) ===')
            if not quiet:
                for pin in pins:
                    lines.append(
                        f'  - Pin #{pin["id"]} by {pin["submitter"]}: {pin["description"]}'
                    )
            lines.append('')

        if self.orphan_result is not None:
            lines.append('=== 删除孤儿文件结果 ===')
            lines.append(f'已删除: {self.orphan_result.get("deleted_count", 0)} 个')
            if not quiet and self.orphan_result.get('deleted_files'):
                for file in self.orphan_result['deleted_files']:
                    lines.append(f'  ✓ {file}')
            if self.orphan_result.get('errors'):
                lines.append(f'失败: {len(self.orphan_result["errors"])} 个')
                if not quiet:
                    for error in self.orphan_result['errors']:
                        lines.append(f'  ✗ {error["path"]}: {error["error"]}')
            lines.append('')

        if self.missing_result is not None:
            lines.append('=== 修复缺失文件结果 ===')
            lines.append(f'删除Image记录: {self.missing_result.get("fixed_images", 0)} 个')
            lines.append(f'删除Thumbnail记录: {self.missing_result.get("fixed_thumbnails", 0)} 个')
            lines.append(f'删除Pin记录: {self.missing_result.get("fixed_pins", 0)} 个')
            if self.missing_result.get('errors'):
                lines.append(f'失败: {len(self.missing_result["errors"])} 个')
                if not quiet:
                    for error in self.missing_result['errors']:
                        lines.append(f'  ✗ {error["path"]} ({error["type"]}): {error["error"]}')
            lines.append('')

        lines.append('巡检完成！')
        return '\n'.join(lines)
