import os
import json

from django.conf import settings
from django.core.management.base import BaseCommand

from core.utils import (
    run_media_check,
    delete_orphan_files,
    fix_missing_files,
    save_report,
    DEFAULT_MAX_DEPTH,
    DEFAULT_EXCLUDE_DIRS,
)


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
            help='将报告保存到指定文件路径（JSON格式）',
        )
        parser.add_argument(
            '--max-depth',
            type=int,
            dest='max_depth',
            default=DEFAULT_MAX_DEPTH,
            help=f'目录扫描最大深度，默认: {DEFAULT_MAX_DEPTH}',
        )
        parser.add_argument(
            '--exclude',
            action='append',
            dest='exclude_dirs',
            default=None,
            help=f'要排除的目录名，可多次指定，默认排除: {", ".join(sorted(DEFAULT_EXCLUDE_DIRS))}',
        )

    def _print_text_report(self, result, quiet, delete_orphans, fix_missing):
        media_root = result['media_root']
        self.stdout.write(f'媒体根目录: {media_root}')
        self.stdout.write(f'扫描时间: {result["scan_time"]}')
        self.stdout.write(f'最大扫描深度: {result["max_depth"]}')
        self.stdout.write(f'排除目录: {", ".join(result["exclude_dirs"])}')
        self.stdout.write('')

        self.stdout.write(self.style.SUCCESS('=== 巡检结果 ==='))
        self.stdout.write(f'文件系统中的文件总数: {result["total_files"]}')
        self.stdout.write(f'数据库中的文件总数: {result["total_db_files"]}')
        self.stdout.write(f'孤儿文件数量: {result["orphan_count"]}')
        self.stdout.write(f'缺失文件数量: {result["missing_count"]}')
        self.stdout.write('')

        if result['orphan_files'] and not quiet:
            self.stdout.write(self.style.WARNING('=== 孤儿文件列表 ==='))
            for file_info in result['orphan_files']:
                self.stdout.write(f'  - {file_info["path"]} ({file_info["size"]} bytes)')
            self.stdout.write('')

        if result['missing_files'] and not quiet:
            self.stdout.write(self.style.WARNING('=== 缺失文件列表 ==='))
            for file in result['missing_files']:
                self.stdout.write(f'  - {file}')
            self.stdout.write('')

        if result['pins_without_image']:
            self.stdout.write(
                self.style.WARNING(
                    f'=== 缺少图片的Pin ({len(result["pins_without_image"])} 个) ==='
                )
            )
            if not quiet:
                for pin in result['pins_without_image']:
                    self.stdout.write(
                        f'  - Pin #{pin["id"]} by {pin["submitter"]}: {pin["description"]}'
                    )
            self.stdout.write('')

        orphan_result = None
        missing_result = None

        if delete_orphans and result['orphan_count'] > 0:
            self.stdout.write(self.style.WARNING('正在删除孤儿文件...'))
            orphan_result = delete_orphan_files(
                max_depth=result['max_depth'],
                exclude_dirs=set(result['exclude_dirs']),
            )
            if not quiet:
                for file in orphan_result['deleted_files']:
                    self.stdout.write(f'  已删除: {file}')
                for error in orphan_result['errors']:
                    self.stdout.write(self.style.ERROR(f'  删除失败 {error["path"]}: {error["error"]}'))
            self.stdout.write(
                self.style.SUCCESS(
                    f'共删除 {orphan_result["deleted_count"]} 个孤儿文件'
                )
            )
            self.stdout.write('')

        if fix_missing and result['missing_count'] > 0:
            self.stdout.write(self.style.WARNING('正在修复缺失文件的数据库记录...'))
            missing_result = fix_missing_files(
                max_depth=result['max_depth'],
                exclude_dirs=set(result['exclude_dirs']),
            )
            if not quiet:
                for error in missing_result['errors']:
                    self.stdout.write(
                        self.style.ERROR(
                            f'  删除失败 {error["path"]} ({error["type"]}): {error["error"]}'
                        )
                    )
            self.stdout.write(
                self.style.SUCCESS(
                    f'共删除 {missing_result["fixed_images"]} 个Image记录, '
                    f'{missing_result["fixed_thumbnails"]} 个Thumbnail记录, '
                    f'{missing_result["fixed_pins"]} 个Pin记录'
                )
            )

        self.stdout.write(self.style.SUCCESS('巡检完成！'))
        return orphan_result, missing_result

    def handle(self, *args, **options):
        delete_orphans = options['delete_orphans']
        fix_missing = options['fix_missing']
        quiet = options['quiet']
        json_output = options['json_output']
        output_path = options['output']
        max_depth = options['max_depth']
        exclude_dirs = options['exclude_dirs']

        if exclude_dirs is not None:
            exclude_dirs = set(exclude_dirs)

        if not json_output:
            self.stdout.write(self.style.SUCCESS('开始媒体目录巡检...'))
            self.stdout.write('=' * 60)

        result = run_media_check(max_depth=max_depth, exclude_dirs=exclude_dirs)

        orphan_result = None
        missing_result = None

        if json_output:
            if delete_orphans and result['orphan_count'] > 0:
                orphan_result = delete_orphan_files(
                    max_depth=max_depth,
                    exclude_dirs=exclude_dirs,
                )
                result['delete_orphans_result'] = orphan_result

            if fix_missing and result['missing_count'] > 0:
                missing_result = fix_missing_files(
                    max_depth=max_depth,
                    exclude_dirs=exclude_dirs,
                )
                result['fix_missing_result'] = missing_result

            output_data = result
        else:
            orphan_result, missing_result = self._print_text_report(
                result, quiet, delete_orphans, fix_missing
            )
            output_data = result

        if output_path:
            saved_path = save_report(output_data, output_path)
            if not json_output:
                self.stdout.write(self.style.SUCCESS(f'报告已保存到: {saved_path}'))

        if json_output:
            self.stdout.write(json.dumps(output_data, ensure_ascii=False, indent=2))

        return result
