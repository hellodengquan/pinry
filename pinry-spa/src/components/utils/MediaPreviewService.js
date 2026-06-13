const IMAGE_EXTENSIONS = [
  '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg',
  '.tiff', '.tif', '.ico',
];

const VIDEO_EXTENSIONS = [
  '.mp4', '.webm', '.ogg', '.ogv', '.mov', '.avi',
];

const YOUTUBE_PATTERN = /^(https?:\/\/)?(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{11})/i;
const VIMEO_PATTERN = /^(https?:\/\/)?(www\.)?vimeo\.com\/(\d+)/i;

function escapeUrl(url) {
  try {
    const uri = new URL(url);
    return uri.pathname;
  } catch (e) {
    return url;
  }
}

function detectVideoProvider(url) {
  if (!url) return null;
  if (YOUTUBE_PATTERN.test(url)) return 'youtube';
  if (VIMEO_PATTERN.test(url)) return 'vimeo';
  return null;
}

function getYoutubeThumbnail(url) {
  const match = url.match(YOUTUBE_PATTERN);
  if (match && match[4]) {
    return `https://img.youtube.com/vi/${match[4]}/hqdefault.jpg`;
  }
  return null;
}

function getVimeoThumbnail(url) {
  const match = url.match(VIMEO_PATTERN);
  if (match && match[3]) {
    return `https://i.vimeocdn.com/video/${match[3]}_640.jpg`;
  }
  return null;
}

function getProviderThumbnail(url) {
  const provider = detectVideoProvider(url);
  if (provider === 'youtube') return getYoutubeThumbnail(url);
  if (provider === 'vimeo') return getVimeoThumbnail(url);
  return null;
}

function detectMediaType(url) {
  if (!url) return 'unknown';

  if (detectVideoProvider(url)) return 'video';

  const lowerUrl = url.toLowerCase().split('?')[0].split('#')[0];

  for (let i = 0; i < VIDEO_EXTENSIONS.length; i++) {
    if (lowerUrl.endsWith(VIDEO_EXTENSIONS[i])) return 'video';
  }

  for (let i = 0; i < IMAGE_EXTENSIONS.length; i++) {
    if (lowerUrl.endsWith(IMAGE_EXTENSIONS[i])) return 'image';
  }

  if (/^https?:\/\//i.test(url)) return 'web_link';

  return 'unknown';
}

function formatDuration(seconds) {
  if (!seconds) return null;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function buildDisplayItem(pin) {
  const mediaType = detectMediaType(pin.url);
  const provider = detectVideoProvider(pin.url);
  const thumbnail = pin.image && pin.image.thumbnail
    ? pin.image.thumbnail
    : null;
  const original = pin.image ? pin.image.image : null;
  const oembed = pin.metadata && pin.metadata.oembed ? pin.metadata.oembed : null;
  const providerThumbnail = getProviderThumbnail(pin.url);

  const item = {
    id: pin.id,
    mediaType: mediaType,
    url: thumbnail ? escapeUrl(thumbnail.image) : (original ? escapeUrl(original) : null),
    largeImageUrl: original ? escapeUrl(original) : null,
    originalImageUrl: pin.url || null,
    referer: pin.referer || null,
    description: pin.description || '',
    tags: pin.tags || [],
    private: pin.private || false,
    author: pin.submitter ? pin.submitter.username : '',
    avatar: pin.submitter ? `//gravatar.com/avatar/${pin.submitter.gravatar}` : '',
    ownerId: pin.submitter ? pin.submitter.id : null,
    style: {},
    class: {},
    provider: provider,
    title: (pin.metadata && pin.metadata.title) || '',
    duration: (pin.metadata && pin.metadata.duration) ? formatDuration(pin.metadata.duration) : null,
    providerThumbnail: providerThumbnail,
  };

  if (pin.image) {
    item.originalWidth = pin.image.width;
    item.originalHeight = pin.image.height;
    if (thumbnail) {
      item.style = {
        width: `${thumbnail.width}px`,
        height: `${thumbnail.height}px`,
      };
    }
  }

  if (mediaType === 'video') {
    item.videoUrl = pin.url;
    if (oembed && oembed.thumbnail_url) {
      item.url = oembed.thumbnail_url;
      item.largeImageUrl = oembed.thumbnail_url;
    } else if (providerThumbnail) {
      item.url = providerThumbnail;
      item.largeImageUrl = providerThumbnail;
    }
  }

  if (mediaType === 'web_link') {
    item.webLinkUrl = pin.url;
  }

  return item;
}

function buildPreviewItem(displayItem) {
  return {
    id: displayItem.id,
    mediaType: displayItem.mediaType,
    largeImageUrl: displayItem.largeImageUrl,
    originalImageUrl: displayItem.originalImageUrl,
    referer: displayItem.referer,
    description: displayItem.description,
    tags: displayItem.tags,
    author: displayItem.author,
    avatar: displayItem.avatar,
    videoUrl: displayItem.videoUrl || null,
    webLinkUrl: displayItem.webLinkUrl || null,
    provider: displayItem.provider || null,
    title: displayItem.title || '',
    duration: displayItem.duration || null,
    providerThumbnail: displayItem.providerThumbnail || null,
  };
}

function buildFormModel(existingPin) {
  if (!existingPin) {
    return {
      url: '',
      referer: '',
      description: '',
      tags: [],
      private: false,
    };
  }

  return {
    url: existingPin.url || existingPin.originalImageUrl || '',
    referer: existingPin.referer || '',
    description: existingPin.description || '',
    tags: existingPin.tags || [],
    private: existingPin.private || false,
  };
}

function buildUploadPreview(uploadedImage) {
  if (!uploadedImage) return null;
  return {
    mediaType: 'image',
    imageId: uploadedImage.id,
    previewUrl: uploadedImage.thumbnail
      ? escapeUrl(uploadedImage.thumbnail.image)
      : escapeUrl(uploadedImage.image),
    width: uploadedImage.width,
    height: uploadedImage.height,
  };
}

export default {
  detectMediaType,
  detectVideoProvider,
  escapeUrl,
  buildDisplayItem,
  buildPreviewItem,
  buildFormModel,
  buildUploadPreview,
  formatDuration,
  getProviderThumbnail,
};
