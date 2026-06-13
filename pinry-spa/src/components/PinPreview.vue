<template>
  <div class="pin-preview-modal">
    <section>
        <div class="card">
          <div class="card-image" v-if="previewItem.mediaType === 'image'">
            <figure class="image">
              <img :src="previewItem.largeImageUrl" alt="Image">
            </figure>
          </div>
          <div class="card-image video-preview" v-else-if="previewItem.mediaType === 'video'">
            <div class="video-container">
              <div class="video-meta-overlay" v-if="previewItem.title || previewItem.duration">
                <span class="video-title" v-if="previewItem.title">{{ previewItem.title }}</span>
                <span class="video-duration" v-if="previewItem.duration">{{ previewItem.duration }}</span>
              </div>
              <video :src="previewItem.videoUrl" controls class="preview-video" :poster="previewItem.providerThumbnail || previewItem.largeImageUrl"></video>
            </div>
          </div>
          <div class="card-image link-preview" v-else-if="previewItem.mediaType === 'web_link'">
            <a :href="previewItem.webLinkUrl" target="_blank" class="link-preview-card">
              <b-icon icon="link" size="is-large"></b-icon>
              <p class="link-url">{{ previewItem.webLinkUrl }}</p>
            </a>
            <img v-if="previewItem.largeImageUrl" :src="previewItem.largeImageUrl" alt="Preview">
          </div>
          <div class="card-image blocked-preview" v-else-if="previewItem.mediaType === 'blocked'">
            <div class="blocked-notice">
              <b-icon icon="lock" size="is-large" type="is-danger"></b-icon>
              <p>Content blocked for security reasons</p>
            </div>
          </div>
          <div class="card-image unknown-preview" v-else>
            <div class="unknown-notice">
              <b-icon icon="help-circle" size="is-large"></b-icon>
              <p>Unsupported media type</p>
            </div>
          </div>
          <div class="card-content">
            <div class="content">
                <p class="description title" v-html="niceLinks(previewItem.description)"></p>
            </div>
            <div class="media">
              <div class="media-left">
                <figure class="image is-48x48">
                  <img :src="previewItem.avatar" alt="Image">
                </figure>
              </div>
              <div class="media-content">
                <div class="is-pulled-left">
                  <p class="title is-4 pin-meta-info"><span class="dim">{{ $t("pinnedByTitle") }}</span><span class="author">{{ previewItem.author }}</span></p>
                  <p class="subtitle is-6" v-show="previewItem.tags.length > 0">
                    <span class="subtitle dim">in&nbsp;</span>
                    <template v-for="tag in previewItem.tags">
                      <b-tag v-bind:key="tag" type="is-info" class="pin-preview-tag">{{ tag }}</b-tag>
                    </template>
                  </p>
                </div>
                <div class="is-pulled-right">
                  <a :href="previewItem.referer" target="_blank">
                    <b-button
                        v-show="previewItem.referer !== null"
                        class="meta-link"
                        type="is-warning">
                      {{ $t("sourceButton") }}
                    </b-button>
                  </a>
                  <a :href="previewItem.originalImageUrl" target="_blank">
                    <b-button
                        v-show="previewItem.originalImageUrl !== null"
                        class="meta-link"
                        type="is-link">
                        {{ $t("originalImageButton") }}
                    </b-button>
                  </a>
                  <b-button
                      @click="closeAndGoTo"
                      class="meta-link"
                      type="is-success">
                      {{ $t("permalinkButton") }}
                  </b-button>
                </div>
              </div>
            </div>
          </div>
        </div>
    </section>
  </div>
</template>

<script>
import MediaPreviewService from './utils/MediaPreviewService';
import niceLinks from './utils/niceLinks';

export default {
  name: 'PinPreview',
  props: ['pinItem'],
  computed: {
    previewItem() {
      return MediaPreviewService.buildPreviewItem(this.pinItem);
    },
  },
  methods: {
    closeAndGoTo() {
      this.$parent.close();
      this.$router.push(
        { name: 'pin', params: { pinId: this.pinItem.id } },
      );
    },
    niceLinks,
  },
};
</script>

<style lang="scss" scoped>
@import './utils/fonts.scss';

.meta-link {
  margin-left: 0.3rem;
}
.dim {
  @include secondary-font-color-in-dark;
}
.pin-meta-info {
  line-height: 16px;
}
.card {
  background-color: rgba(0, 0, 0, 0.6);
  .content {
    border-bottom: 1px solid #333;
  }
  .card-content {
    .author {
      @include title-font-color-in-dark;
    }
    padding: 0;
    .content {
      padding: 0.3rem;
      margin-bottom: 0;
    }
    .media {
      padding: 0.3rem;
    }
  }
  .description {
    @include title-font;
    @include title-font-color-in-dark;
    font-size: 16px;
    padding: 8px;
  }
}
.pin-preview-tag {
  margin-right: 0.2rem;
  margin-bottom: 2px;
}
/* preview size should always less then screen */
.card-image img {
  padding: 10px;
  margin-left: auto;
  margin-right: auto;
  width: auto;
}
.video-preview .preview-video {
  max-width: 100%;
  max-height: 70vh;
  display: block;
  margin: 0 auto;
}
.video-container {
  position: relative;
  text-align: center;
  padding: 10px;
}
.video-meta-overlay {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 10px;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: linear-gradient(to bottom, rgba(0,0,0,0.7), transparent);
  color: #fff;
}
.video-title {
  font-weight: 600;
  font-size: 14px;
  max-width: 70%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.video-duration {
  font-size: 13px;
  font-family: monospace;
  background: rgba(0,0,0,0.5);
  padding: 2px 6px;
  border-radius: 3px;
}
.link-preview-card {
  display: block;
  text-align: center;
  padding: 40px 20px;
  color: #fff;
  .link-url {
    margin-top: 10px;
    word-break: break-all;
    font-size: 14px;
  }
}
.blocked-preview .blocked-notice,
.unknown-preview .unknown-notice {
  text-align: center;
  padding: 60px 20px;
  color: #aaa;
  p {
    margin-top: 12px;
    font-size: 14px;
  }
}
</style>
