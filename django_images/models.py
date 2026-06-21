import hashlib
import os.path
from io import BytesIO

from django.db import models
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.dispatch import receiver
from PIL import Image as PILImage

from importlib import import_module

from django.urls import reverse

from . import utils
from .settings import IMAGE_SIZES, IMAGE_PATH, IMAGE_AUTO_DELETE


def calculate_md5(file_obj):
    hasher = hashlib.md5()
    file_obj.seek(0)
    for chunk in iter(lambda: file_obj.read(8192), b''):
        hasher.update(chunk)
    file_obj.seek(0)
    return hasher.hexdigest()


PHASH_THRESHOLD_SAMPLES = [
    {
        "threshold": 0,
        "name": "完全相同",
        "hit_samples": ["PNG→JPG 仅转格式", "文件重命名", "仅修改 EXIF 拍摄时间"],
        "miss_samples": ["任何图像内容修改"],
        "false_positive_rate": "≈ 0%",
        "recommended_scenario": "法律取证、版权严格去重",
    },
    {
        "threshold": 2,
        "name": "极相似",
        "hit_samples": ["质量 95→50 的 JPG 压缩", "去除隐形水印", "色彩空间 sRGB→AdobeRGB"],
        "miss_samples": ["添加可见水印、±10% 以上亮度调整"],
        "false_positive_rate": "< 0.01%",
        "recommended_scenario": "素材库、严格设计稿版本管理",
    },
    {
        "threshold": 5,
        "name": "相似（推荐默认）",
        "hit_samples": [
            "2000×2000 → 800×800 缩放",
            "居中裁剪 80% 以上保留主体",
            "Instagram/Lightroom 常规滤镜",
            "±20% 亮度/对比度调整",
            "添加右下角小尺寸 Logo 水印",
        ],
        "miss_samples": [
            "左右/上下镜像翻转",
            "主体旋转 45° 以上",
            "50% 以上区域被遮挡/裁切",
            "完全不同的两张同类图片（如两只不同的猫）",
        ],
        "false_positive_rate": "≈ 0.1%",
        "recommended_scenario": "Pinry 默认推荐，平衡误报与漏报",
    },
    {
        "threshold": 7,
        "name": "宽松相似",
        "hit_samples": [
            "添加大段文字的 meme 图",
            "手机端 vs 桌面端同场景截图",
            "不同光线的同角度实拍照片",
            "黑白 vs 彩色同一照片",
        ],
        "miss_samples": ["同场景不同时间（白天/黑夜）、完全不同主体"],
        "false_positive_rate": "≈ 2~3%",
        "recommended_scenario": "内容聚类、相似推荐辅助信号",
    },
    {
        "threshold": 10,
        "name": "粗略分类",
        "hit_samples": ["同色系风格插画、同构图不同照片（蓝天下的山）"],
        "miss_samples": ["大部分跨类别图片"],
        "false_positive_rate": "> 10%",
        "recommended_scenario": "仅用于粗粒度分类标签辅助，不用于重复检测",
    },
]


def calculate_phash(file_obj):
    """
    计算平均感知哈希（aHash / meanHash）

    算法原理：
      1. 将图片缩放到 8x8 = 64 像素
      2. 转为灰度图（单通道 L）
      3. 计算 64 个像素的平均值
      4. 逐个像素与平均值比较，得到 64 位二进制指纹
      5. 转为 16 字符十六进制字符串存储

    汉明距离推荐阈值（结合实际业务，详见常量 PHASH_THRESHOLD_SAMPLES）：
      距离 0    : 完全相同    → 格式转换 / 重命名 / 仅 EXIF 信息变更
      距离 1-2  : 极相似      → 压缩等级变化 / 去隐形水印 / 色彩空间转换
      距离 3-4  : 高度相似    → 去水印 / 轻微调色 / 小幅缩放
      距离 5    : 【平衡推荐】→ 兼容缩放、裁剪、常规滤镜（默认值，业界通用）
      距离 6-7  : 宽松相似    → 可识别二次编辑、加文字，误报率上升
      距离 8-9  : 近似分类    → 仅用于同类别粗粒度识别
      距离 10+  : 粗略分类    → 不建议用于重复检测
    """
    try:
        file_obj.seek(0)
        img = PILImage.open(file_obj)
        img = img.convert('L').resize((8, 8), PILImage.Resampling.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / 64
        bits = ''.join('1' if p > avg else '0' for p in pixels)
        file_obj.seek(0)
        return '%016x' % int(bits, 2)
    except Exception:
        file_obj.seek(0)
        return None


def hamming_distance(hash1, hash2):
    """
    计算两个 pHash 的汉明距离

    返回值说明：
      - 0  : 完全一致
      - <=5: 视为相似图片（默认阈值）
      - >5 : 视为不同图片
      - 999: 任一 hash 为空，无法比较
    """
    if hash1 is None or hash2 is None:
        return 999
    return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')


def hashed_upload_to(instance, filename, **kwargs):
    image_type = 'original' if isinstance(instance, Image) else 'thumbnail'
    prefix = 'image/%s/by-md5/' % (image_type,)
    hasher = hashlib.md5()
    for chunk in instance.image.chunks():
        hasher.update(chunk)
    hash_ = hasher.hexdigest()
    base, ext = os.path.splitext(filename)
    return '%(prefix)s%(first)s/%(second)s/%(hash)s/%(base)s%(ext)s' % {
        'prefix': prefix,
        'first': hash_[0],
        'second': hash_[1],
        'hash': hash_,
        'base': base,
        'ext': ext,
    }


if IMAGE_PATH is None:
    upload_to = hashed_upload_to
else:
    if callable(IMAGE_PATH):
        upload_to = IMAGE_PATH
    else:
        parts = IMAGE_PATH.split('.')
        module_name = '.'.join(parts[:-1])
        module = import_module(module_name)
        upload_to = getattr(module, parts[-1])


class Image(models.Model):
    image = models.ImageField(upload_to=upload_to,
                              height_field='height', width_field='width',
                              max_length=255)
    height = models.PositiveIntegerField(default=0, editable=False)
    width = models.PositiveIntegerField(default=0, editable=False)
    hash = models.CharField(max_length=32, blank=True, null=True, db_index=True, editable=False)
    phash = models.CharField(max_length=16, blank=True, null=True, db_index=True, editable=False)

    def save(self, *args, **kwargs):
        if self.image:
            if not self.hash:
                self.hash = calculate_md5(self.image)
            if not self.phash:
                self.phash = calculate_phash(self.image)
        super(Image, self).save(*args, **kwargs)

    def find_similar(self, max_distance=5):
        """
        查找相似图片

        Args:
            max_distance: 汉明距离阈值，默认 5（平衡推荐值）

        建议的阈值选择建议：
            max_distance=2 → 仅极相似
            max_distance=5 → 相似（推荐默认）
            max_distance=8 → 宽松匹配
        """
        if not self.phash:
            return Image.objects.none()
        similar = []
        for img in Image.objects.exclude(id=self.id).filter(phash__isnull=False):
            if hamming_distance(self.phash, img.phash) <= max_distance:
                similar.append(img)
        return similar

    def get_by_size(self, size):
        return self.thumbnail_set.get(size=size)

    def get_absolute_url(self, size=None):
        if not size:
            return self.image.url
        try:
            return self.get_by_size(size).image.url
        except Thumbnail.DoesNotExist:
            return reverse('image-thumbnail', args=(self.id, size))


class ThumbnailManager(models.Manager):
    def get_or_create_at_sizes(self, image, sizes):
        sizes_to_create = list(sizes)
        sized = {}
        for size in sizes:
            if size not in IMAGE_SIZES:
                raise ValueError("Received unknown size: %s" % size)

            try:
                sized[size] = image.get_by_size(size)
            except Thumbnail.DoesNotExist:
                pass
            else:
                sizes_to_create.remove(size)

        if sizes_to_create:
            bufs = [
                utils.write_image_in_memory(img)
                for img in utils.scale_and_crop_iter(
                    image.image,
                    [IMAGE_SIZES[size] for size in sizes_to_create])
            ]
            for size, buf in zip(sizes_to_create, bufs):
                # and save to storage
                original_dir, original_file = os.path.split(image.image.name)
                thumb_file = InMemoryUploadedFile(buf, "image", original_file,
                                                  None, buf.tell(), None)
                sized[size], created = image.thumbnail_set.get_or_create(
                    size=size, defaults={'image': thumb_file})

        # Make sure this is in the correct order
        return [sized[size] for size in sizes]


class Thumbnail(models.Model):
    original = models.ForeignKey(Image, on_delete=models.CASCADE)
    image = models.ImageField(upload_to=upload_to,
                              height_field='height', width_field='width',
                              max_length=255)
    size = models.CharField(max_length=100)
    height = models.PositiveIntegerField(default=0, editable=False)
    width = models.PositiveIntegerField(default=0, editable=False)

    objects = ThumbnailManager()

    class Meta:
        unique_together = ('original', 'size')

    def get_absolute_url(self):
        return self.image.url


@receiver(models.signals.post_save)
def original_changed(sender, instance, created, **kwargs):
    if isinstance(instance, Image):
        instance.thumbnail_set.all().delete()


@receiver(models.signals.post_delete)
def delete_image_files(sender, instance, **kwargs):
    if isinstance(instance, (Image, Thumbnail)) and IMAGE_AUTO_DELETE:
        if instance.image.storage.exists(instance.image.name):
            instance.image.delete(save=False)
