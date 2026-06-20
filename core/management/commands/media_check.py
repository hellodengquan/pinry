import os

from django.conf import settings
from django.core.management.base import BaseCommand

from core.utils import (
    run_media_check,
    delete_orphan_files,
    fix_missing_files,
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

    def handle(self, *args, **options):
        delete_orphans = options['delete_orphans']
        fix_missing = options['fix_missing']
        quiet = options['quiet']

        self.stdout.write(self.style.SUCCESS('开始媒体目录巡检...'))
        self.stdout.write('=' * 60)

        result = run_media_check()
        media_root = result['media_root']
        self.stdout.write(f'媒体根目录: {media_root}')
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

        if delete_orphans and result['orphan_count'] > 0:
            self.stdout.write(self.style.WARNING('正在删除孤儿文件...'))
            orphan_result = delete_orphan_files()
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
            missing_result = fix_missing_files()
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

        return result
