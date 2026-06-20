import os
import json
import sys

from django.core.management.base import BaseCommand

from core.utils import (
    run_media_check,
    delete_orphan_files,
    fix_missing_files,
    MediaCheckRenderer,
    get_audit_log_retention_days,
    auto_cleanup_audit_logs_if_needed,
)
from core.models import MediaCheckAuditLog


class Command(BaseCommand):
    help = '检查媒体目录的完整性，报告孤儿文件和缺失图片'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete-orphans',
            action='store_true',
            dest='delete_orphans',
            default=False,
            help='删除孤儿文件（存在于文件系统但不在数据库中的文件）',
        )
        parser.add_argument(
            '--fix-missing',
            action='store_true',
            dest='fix_missing',
            default=False,
            help='修复缺失图片（删除数据库中对应记录）',
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            dest='quiet',
            default=False,
            help='静默模式，只输出汇总信息',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            dest='json_output',
            default=False,
            help='以JSON格式输出结果（适合CI/CD流水线）',
        )
        parser.add_argument(
            '--output',
            type=str,
            dest='output',
            default=None,
            help='将报告保存到指定文件路径（支持 .json 和 .txt）',
        )
        parser.add_argument(
            '--output-format',
            type=str,
            dest='output_format',
            choices=['json', 'text'],
            default=None,
            help='输出文件格式（默认根据文件后缀推断）',
        )
        parser.add_argument(
            '--max-depth',
            type=int,
            dest='max_depth',
            default=None,
            help='目录扫描最大深度',
        )
        parser.add_argument(
            '--exclude',
            action='append',
            dest='exclude_dirs',
            default=None,
            help='要排除的目录名/glob 模式，可多次指定（例如 ".cache_*"）',
        )
        parser.add_argument(
            '--no-audit',
            action='store_true',
            dest='no_audit',
            default=False,
            help='不记录审计日志',
        )
        parser.add_argument(
            '--no-auto-cleanup',
            action='store_true',
            dest='no_auto_cleanup',
            default=False,
            help='禁用自动清理过期审计日志',
        )
        parser.add_argument(
            '--cleanup-old',
            action='store_true',
            dest='cleanup_old',
            default=False,
            help='仅清理过期的审计日志然后退出',
        )
        parser.add_argument(
            '--retention-days',
            type=int,
            dest='retention_days',
            default=None,
            help='审计日志保留天数',
        )
        parser.add_argument(
            '--auto',
            action='store_true',
            dest='auto_mode',
            default=False,
            help='cron 友好模式：启用 --json --quiet --delete-orphans --fix-missing + 自动清理',
        )

    def _determine_action(self, delete_orphans, fix_missing):
        if delete_orphans and fix_missing:
            return MediaCheckAuditLog.ACTION_ALL
        elif delete_orphans:
            return MediaCheckAuditLog.ACTION_DELETE_ORPHANS
        elif fix_missing:
            return MediaCheckAuditLog.ACTION_FIX_MISSING
        return MediaCheckAuditLog.ACTION_CHECK

    def _detect_output_format(self, output_path, explicit_format):
        if explicit_format:
            return explicit_format
        if output_path:
            lower = output_path.lower()
            if lower.endswith('.json'):
                return 'json'
            if lower.endswith('.txt') or lower.endswith('.log'):
                return 'text'
        return 'json'

    def _write_console_text(self, renderer, quiet):
        for line in renderer.iter_text(quiet=quiet):
            if '孤儿文件' in line or '缺失文件' in line or '缺少图片的Pin' in line:
                self.stdout.write(self.style.WARNING(line))
            elif '已删除' in line or '删除Image' in line or '删除Thumbnail' in line or '删除Pin' in line:
                self.stdout.write(self.style.SUCCESS(line))
            elif '失败' in line or '✗' in line:
                self.stdout.write(self.style.ERROR(line))
            elif '=== 巡检结果 ===' in line or '巡检完成' in line:
                self.stdout.write(self.style.SUCCESS(line))
            else:
                self.stdout.write(line)

    def handle(self, *args, **options):
        auto_mode = options['auto_mode']

        if auto_mode:
            options['json_output'] = True
            options['quiet'] = True
            options['delete_orphans'] = True
            options['fix_missing'] = True
            options['no_auto_cleanup'] = False

        delete_orphans = options['delete_orphans']
        fix_missing = options['fix_missing']
        quiet = options['quiet']
        json_output = options['json_output']
        output_path = options['output']
        output_format = self._detect_output_format(output_path, options['output_format'])
        max_depth = options['max_depth']
        exclude_dirs = options['exclude_dirs']
        no_audit = options['no_audit']
        no_auto_cleanup = options['no_auto_cleanup']
        cleanup_old = options['cleanup_old']
        retention_days = options['retention_days']

        if exclude_dirs is not None:
            exclude_dirs = set(exclude_dirs)

        if cleanup_old:
            cleaned = MediaCheckAuditLog.cleanup_old_logs(retention_days)
            if not json_output:
                days = retention_days if retention_days else get_audit_log_retention_days()
                self.stdout.write(self.style.SUCCESS(f'已清理 {cleaned} 条过期审计日志（保留 {days} 天）'))
            else:
                self.stdout.write(json.dumps({'cleaned_count': cleaned}, ensure_ascii=False))
            return cleaned

        if not json_output and not quiet:
            self.stdout.write(self.style.SUCCESS('开始媒体目录巡检...'))
            self.stdout.write('=' * 60)

        cleaned_count = 0
        if not no_auto_cleanup:
            try:
                cleaned_count = auto_cleanup_audit_logs_if_needed(retention_days)
            except Exception:
                cleaned_count = 0

        result = run_media_check(max_depth=max_depth, exclude_dirs=exclude_dirs)

        orphan_result = None
        missing_result = None

        if delete_orphans and result['orphan_count'] > 0:
            orphan_result = delete_orphan_files(
                max_depth=max_depth,
                exclude_dirs=exclude_dirs,
            )

        if fix_missing and result['missing_count'] > 0:
            missing_result = fix_missing_files(
                max_depth=max_depth,
                exclude_dirs=exclude_dirs,
            )

        renderer = MediaCheckRenderer(
            report=result,
            orphan_result=orphan_result,
            missing_result=missing_result,
        )

        if not no_audit:
            try:
                action = self._determine_action(delete_orphans, fix_missing)
                full_report = renderer.to_dict()
                MediaCheckAuditLog.create_from_report(
                    report=full_report,
                    action=action,
                    success=True,
                )
            except Exception:
                pass

        if output_path:
            saved_path = renderer.write_to_file(output_path, format=output_format)
            if not json_output:
                self.stdout.write(self.style.SUCCESS(f'报告已保存到: {saved_path}'))

        if cleaned_count > 0 and not json_output and not quiet:
            days = retention_days if retention_days else get_audit_log_retention_days()
            self.stdout.write(self.style.SUCCESS(f'自动清理 {cleaned_count} 条过期审计日志（保留 {days} 天）'))

        if json_output:
            renderer.write_json_to(self.stdout)
            self.stdout.write('\n')
        else:
            self._write_console_text(renderer, quiet)

        return result
