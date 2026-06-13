const IMAGE_EXTENSIONS = [
  '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg',
  '.tiff', '.tif', '.ico',
];

const VIDEO_EXTENSIONS = [
  '.mp4', '.webm', '.ogg', '.ogv', '.mov', '.avi',
];

function escapeUrl(url) {
  try {
    const uri = new URL(url);
    return uri.pathname;
  } catch (e) {
    return url;
  }
}

function detectMediaType(url) {
  if (!url) return 'unknown';

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

function buildDisplayItem(pin) {
  const mediaType = detectMediaType(pin.url);
  const thumbnail = pin.image && pin.image.thumbnail
    ? pin.image.thumbnail
    : null;
  const original = pin.image ? pin.image.image : null;

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
  escapeUrl,
  buildDisplayItem,
  buildPreviewItem,
  buildFormModel,
  buildUploadPreview,
};
