<template>
  <div class="image-upload">
    <div
      v-show="previewImage !== null"
      class="has-text-centered is-center preview">
      <img :src="previewImage">
    </div>
    <div v-show="previewImage === null">
      <b-field>
        <b-upload v-model="dropFile"
                  accept="image/*"
                  :loading="loading"
                  drag-drop>
          <section class="section">
            <div class="content has-text-centered">
              <p>
                <b-icon
                  icon="upload"
                  size="is-medium">
                </b-icon>
              </p>
              <p>{{ $t("FileUploadDescription") }}</p>
            </div>
          </section>
        </b-upload>
      </b-field>
    </div>
  </div>
</template>

<script>
import API from '../api';
import MediaPreviewService from '../utils/MediaPreviewService';

export default {
  name: 'FileUpload',
  data() {
    return {
      dropFile: null,
      loading: false,
      uploadedImage: null,
    };
  },
  props: {
    previewImageURL: {
      type: String,
      default: null,
    },
  },
  watch: {
    dropFile(newFile) {
      this.$emit('imageUploadProcessing');
      this.loading = true;
      API.Pin.uploadImage(newFile).then(
        (resp) => {
          this.uploadedImage = MediaPreviewService.buildUploadPreview(resp.data);
          this.loading = false;
          this.$emit('imageUploadSucceed', this.uploadedImage.imageId);
        },
        () => {
          this.loading = false;
          this.$emit('imageUploadFailed');
        },
      );
    },
  },
  computed: {
    previewImage() {
      if (this.previewExists()) {
        return this.previewImageURL;
      }
      if (this.uploadedImage !== null) {
        return this.uploadedImage.previewUrl;
      }
      return null;
    },
  },
  methods: {
    previewExists() {
      return this.previewImageURL !== null && this.previewImageURL !== '';
    },
  },
};
</script>

<style lang="scss" scoped>
@import '../utils/pin';
@import '../utils/loader';

.preview > img {
  width: $pin-preview-width;
  height: auto;
  @include loader('../../assets/loader.gif');
}

</style>
