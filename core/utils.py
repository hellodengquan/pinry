import hashlib
import os
import json
import datetime
import fnmatch
from io import StringIO

from django.conf import settings


DEFAULT_EXCLUDE_DIRS = {'.git', '.svn', '.hg', '.DS_Store', '__pycache__', 'node_modules', 'tmp', 'temp'}
DEFAULT_MAX_DEPTH = 10
DEFAULT_AUDIT_LOG_RETENTION_DAYS = 90
DEFAULT_AUTO_CLEANUP_AUDIT_LOGS = True


def _get_setting(name, default):
    return getattr(settings, name, default)


def get_exclude_dirs():
    config_exclude = _get_setting('MEDIA_CHECK_EXCLUDE_DIRS', None)
    if config_exclude is None:
        return set(DEFAULT_EXCLUDE_DIRS)
    return set(DEFAULT_EXCLUDE_DIRS) | set(config_exclude)


def get_exclude_dir_patterns():
    config_exclude = _get_setting('MEDIA_CHECK_EXCLUDE_DIRS', None)
    all_patterns = set(DEFAULT_EXCLUDE_DIRS)
    if config_exclude is not None:
        all_patterns.update(config_exclude)
    return all_patterns


def _should_exclude_dir(dirname, exclude_patterns):
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(dirname, pattern):
            return True
    if dirname.startswith('.'):
        return True
    return False


def get_max_depth():
    return _get_setting('MEDIA_CHECK_MAX_DEPTH', DEFAULT_MAX_DEPTH)


def get_audit_log_retention_days():
    return _get_setting('MEDIA_CHECK_AUDIT_RETENTION_DAYS', DEFAULT_AUDIT_LOG_RETENTION_DAYS)


def get_auto_cleanup_audit_logs():
    return _get_setting('MEDIA_CHECK_AUTO_CLEANUP_AUDIT_LOGS', DEFAULT_AUTO_CLEANUP_AUDIT_LOGS)


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


def iter_media_files(max_depth=None, exclude_dirs=None):
    if max_depth is None:
        max_depth = get_max_depth()

    exclude_patterns = get_exclude_dir_patterns()
    if exclude_dirs is not None:
        exclude_patterns = exclude_patterns | set(exclude_dirs)

    media_root = settings.MEDIA_ROOT
    if not os.path.exists(media_root):
        return

    base_depth = media_root.rstrip(os.sep).count(os.sep)

    for root, dirs, files in os.walk(media_root):
        current_depth = root.count(os.sep) - base_depth

        dirs[:] = [d for d in dirs if not _should_exclude_dir(d, exclude_patterns)]

        if max_depth is not None and current_depth >= max_depth:
            dirs[:] = []

        for file in files:
            if file.startswith('.'):
                continue
            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, media_root)
            yield relative_path


def get_all_media_files(max_depth=None, exclude_dirs=None):
    return set(iter_media_files(max_depth=max_depth, exclude_dirs=exclude_dirs))


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
    SUMMARY_FIELDS = [
        ('media_root', '媒体根目录'),
        ('scan_time', '扫描时间'),
        ('max_depth', '最大扫描深度'),
        ('exclude_dirs', '排除目录'),
        ('total_files', '文件系统中的文件总数'),
        ('total_db_files', '数据库中的文件总数'),
        ('orphan_count', '孤儿文件数量'),
        ('missing_count', '缺失文件数量'),
    ]

    def __init__(self, report, orphan_result=None, missing_result=None):
        self.report = report
        self.orphan_result = orphan_result
        self.missing_result = missing_result

    def _format_value(self, key, value):
        if key == 'exclude_dirs' and isinstance(value, (list, set, tuple)):
            return ', '.join(str(v) for v in value)
        if key == 'max_depth':
            return str(value)
        return str(value)

    def _iter_summary_lines(self):
        for key, label in self.SUMMARY_FIELDS:
            val = self.report.get(key, '')
            yield f'{label}: {self._format_value(key, val)}'

    def _iter_orphan_lines(self, quiet):
        if quiet:
            return
        orphan_files = self.report.get('orphan_files') or []
        for file_info in orphan_files:
            yield f'  - {file_info["path"]} ({file_info["size"]} bytes)'

    def _iter_missing_lines(self, quiet):
        if quiet:
            return
        missing_files = self.report.get('missing_files') or []
        for file in missing_files:
            yield f'  - {file}'

    def _iter_pins_lines(self, quiet):
        pins = self.report.get('pins_without_image') or []
        count = len(pins)
        yield f'=== 缺少图片的Pin ({count} 个) ==='
        if quiet:
            return
        for pin in pins:
            yield f'  - Pin #{pin["id"]} by {pin["submitter"]}: {pin["description"]}'

    def _iter_delete_orphan_lines(self, quiet):
        if self.orphan_result is None:
            return
        yield '=== 删除孤儿文件结果 ==='
        yield f'已删除: {self.orphan_result.get("deleted_count", 0)} 个'
        if not quiet and self.orphan_result.get('deleted_files'):
            for file in self.orphan_result['deleted_files']:
                yield f'  ✓ {file}'
        if self.orphan_result.get('errors'):
            yield f'失败: {len(self.orphan_result["errors"])} 个'
            if not quiet:
                for error in self.orphan_result['errors']:
                    yield f'  ✗ {error["path"]}: {error["error"]}'

    def _iter_fix_missing_lines(self, quiet):
        if self.missing_result is None:
            return
        yield '=== 修复缺失文件结果 ==='
        yield f'删除Image记录: {self.missing_result.get("fixed_images", 0)} 个'
        yield f'删除Thumbnail记录: {self.missing_result.get("fixed_thumbnails", 0)} 个'
        yield f'删除Pin记录: {self.missing_result.get("fixed_pins", 0)} 个'
        if self.missing_result.get('errors'):
            yield f'失败: {len(self.missing_result["errors"])} 个'
            if not quiet:
                for error in self.missing_result['errors']:
                    yield f'  ✗ {error["path"]} ({error["type"]}): {error["error"]}'

    def iter_text(self, quiet=False):
        for line in self._iter_summary_lines():
            yield line
        yield ''
        yield '=== 巡检结果 ==='
        yield f'文件系统中的文件总数: {self.report.get("total_files", 0)}'
        yield f'数据库中的文件总数: {self.report.get("total_db_files", 0)}'
        yield f'孤儿文件数量: {self.report.get("orphan_count", 0)}'
        yield f'缺失文件数量: {self.report.get("missing_count", 0)}'
        yield ''

        if not quiet and self.report.get('orphan_files'):
            yield '=== 孤儿文件列表 ==='
            for line in self._iter_orphan_lines(quiet):
                yield line
            yield ''

        if not quiet and self.report.get('missing_files'):
            yield '=== 缺失文件列表 ==='
            for line in self._iter_missing_lines(quiet):
                yield line
            yield ''

        if self.report.get('pins_without_image'):
            for line in self._iter_pins_lines(quiet):
                yield line
            yield ''

        for line in self._iter_delete_orphan_lines(quiet):
            yield line
        if self.orphan_result is not None:
            yield ''

        for line in self._iter_fix_missing_lines(quiet):
            yield line
        if self.missing_result is not None:
            yield ''

        yield '巡检完成！'

    def to_text(self, quiet=False):
        return '\n'.join(self.iter_text(quiet=quiet))

    def write_text_to(self, stream, quiet=False):
        for line in self.iter_text(quiet=quiet):
            stream.write(line)
            stream.write('\n')

    def iter_json(self, chunk_size=4096):
        buffer = StringIO()
        self.write_json_to(buffer)
        buffer.seek(0)
        while True:
            chunk = buffer.read(chunk_size)
            if not chunk:
                break
            yield chunk

    def to_json(self):
        from io import StringIO
        buffer = StringIO()
        self.write_json_to(buffer)
        return buffer.getvalue()

    def to_dict(self):
        result = dict(self.report)
        if self.orphan_result is not None:
            result['delete_orphans_result'] = self.orphan_result
        if self.missing_result is not None:
            result['fix_missing_result'] = self.missing_result
        return result

    def write_json_to(self, stream):
        json.dump(self.to_dict(), stream, ensure_ascii=False, indent=2)

    def write_to_file(self, output_path, format='json'):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            if format == 'json':
                self.write_json_to(f)
            else:
                self.write_text_to(f)
        return output_path


def auto_cleanup_audit_logs_if_needed(retention_days=None):
    if not get_auto_cleanup_audit_logs():
        return 0
    from core.models import MediaCheckAuditLog
    return MediaCheckAuditLog.cleanup_old_logs(retention_days)
