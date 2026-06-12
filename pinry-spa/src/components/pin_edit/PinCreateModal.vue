<template>
  <div class="pin-create-modal">
    <div>
      <div class="modal-card" style="width: auto">
        <header class="modal-card-head">
          <p class="modal-card-title">{{ $t(editorMeta.title) }}</p>
        </header>
        <section class="modal-card-body">
          <div class="columns">
            <div class="column">
              <FileUpload
                :previewImageURL="pinModel.form.url.value"
                v-on:imageUploadSucceed="onUploadDone"
                v-on:imageUploadProcessing="onUploadProcessing"
              ></FileUpload>
              <div class="description" v-show="pinModel.form.description.value" v-html="niceLinks(pinModel.form.description.value)"></div>
            </div>
            <div class="column">
              <b-field v-bind:label="$t('imageUrlLabel')"
                       v-show="!disableUrlField && !isEdit"
                       :type="pinModel.form.url.type"
                       :message="pinModel.form.url.error">
                <b-input
                  type="text"
                  v-model="pinModel.form.url.value"
                  v-bind:placeholder="$t('pinCreateModalImageURLPlaceholder')"
                  maxlength="2048"
                >
                </b-input>
              </b-field>
              <b-field v-bind:label="$t('privacyOptionLabel')"
                       :type="pinModel.form.private.type"
                       :message="pinModel.form.private.error">
                <b-checkbox v-model="pinModel.form.private.value">
                    {{ $t("isPrivateCheckbox") }}
                </b-checkbox>
              </b-field>
              <b-field v-bind:label="$t('imageSourceLabel')"
                       :type="pinModel.form.referer.type"
                       :message="pinModel.form.referer.error">
                <b-input
                  type="text"
                  v-model="pinModel.form.referer.value"
                  v-bind:placeholder="$t('pinCreateModalImageSourcePlaceholder')"
                  maxlength="2048"
                >
                </b-input>
              </b-field>
              <b-field v-bind:label="$t('tagsLabel')">
                <b-taginput
                    v-model="pinModel.form.tags.value"
                    :data="editorMeta.filteredTagOptions"
                    autocomplete
                    ellipsis
                    icon="label"
                    :allow-new="true"
                    v-bind:placeholder="$t('pinCreateModalImageTagsPlaceholder')"
                    @typing="getFilteredTags">
                  <template slot-scope="props">
                    <strong>{{ props.option }}</strong>
                  </template>
                  <template slot="empty">
                    {{ $t("pinCreateModalEmptySlot") }}
                  </template>
                </b-taginput>
              </b-field>
              <b-field v-bind:label="$t('descriptionLabel')"
                       :type="pinModel.form.description.type"
                       :message="pinModel.form.description.error">
                <b-input
                  type="textarea"
                  v-model="pinModel.form.description.value"
                  v-bind:placeholder="$t('pinCreateModalImageDescriptionPlaceholder')"
                  maxlength="1024"
                >
                </b-input>
              </b-field>
            </div>
            <div class="column" v-if="!isEdit">
              <FilterSelect
                :allOptions="boardOptions"
                v-on:selected="onSelectBoard"
              ></FilterSelect>
            </div>
          </div>
          <div v-if="duplicatePins.length > 0" class="duplicate-warning">
            <div class="message is-warning">
              <div class="message-header">
                <p>Duplicate Pins Found</p>
              </div>
              <div class="message-body">
                <p>We found {{ duplicatePins.length }} similar pin(s). You can:</p>
                <ul>
                  <li>Merge with an existing pin (tags and boards will be preserved)</li>
                  <li>Create a new pin anyway</li>
                </ul>
                <div class="duplicate-pins-list">
                  <div
                    v-for="pin in duplicatePins"
                    :key="pin.id"
                    class="duplicate-pin-item"
                    @click="selectDuplicatePin(pin)"
                    :class="{ 'is-selected': selectedDuplicatePin && selectedDuplicatePin.id === pin.id }"
                  >
                    <div class="duplicate-pin-thumb">
                      <img :src="pin.image.thumbnail.image" />
                    </div>
                    <div class="duplicate-pin-info">
                      <p class="duplicate-pin-id">#{{ pin.id }}</p>
                      <p class="duplicate-pin-desc">{{ pin.description || 'No description' }}</p>
                      <p class="duplicate-pin-tags">
                        <span v-for="tag in pin.tags" :key="tag" class="tag is-small">{{ tag }}</span>
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
        <footer class="modal-card-foot">
          <button class="button" type="button" @click="$parent.close()">{{ $t("closeButton") }}</button>
          <template v-if="!isEdit">
            <button
              v-if="duplicatePins.length > 0 && selectedDuplicatePin"
              @click="mergeWithSelected"
              class="button is-info">
              Merge with #{{ selectedDuplicatePin.id }}
            </button>
            <button
              v-if="duplicatePins.length > 0"
              @click="forceCreatePin"
              class="button">
              Create Anyway
            </button>
            <button
              @click="createPin"
              class="button is-primary">{{ $t("pinCreateModalCreatePinButton") }}
            </button>
          </template>
          <button
            v-if="isEdit"
            @click="savePin"
            class="button is-primary">{{ $t("pinCreateModalSaveChangesButton") }}
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

import API from '../api';
import FileUpload from './FileUpload.vue';
import FilterSelect from './FilterSelect.vue';
import bus from '../utils/bus';
import ModelForm from '../utils/ModelForm';
import Loading from '../utils/Loading';
import AutoComplete from '../utils/AutoComplete';
import niceLinks from '../utils/niceLinks';


function isURLBlank(url) {
  return url !== null && url === '';
}

const fields = ['url', 'referer', 'description', 'tags', 'private'];

export default {
  name: 'PinCreateModal',
  props: {
    fromUrl: {
      type: Object,
      default: null,
    },
    username: {
      type: String,
      default: null,
    },
    isEdit: {
      type: Boolean,
      default: false,
    },
    existedPin: {
      type: Object,
      default: null,
    },
  },
  components: {
    FileUpload,
    FilterSelect,
  },
  data() {
    const pinModel = ModelForm.fromFields(fields);
    pinModel.form.tags.value = [];
    return {
      disableUrlField: false,
      pinModel,
      formUpload: {
        imageId: null,
      },
      boardId: null,
      boardOptions: [],
      tagOptions: [],
      editorMeta: {
        title: 'NewPinTitle',
        filteredTagOptions: [],
      },
      duplicatePins: [],
      selectedDuplicatePin: null,
    };
  },
  created() {
    this.fetchBoardList();
    this.fetchTagList();
    if (this.isEdit) {
      this.editorMeta.title = 'EditPinTitle';
      this.pinModel.form.url.value = this.existedPin.url;
      this.pinModel.form.referer.value = this.existedPin.referer;
      this.pinModel.form.description.value = this.existedPin.description;
      this.pinModel.form.tags.value = this.existedPin.tags;
      this.pinModel.form.private.value = this.existedPin.private;
    } else {
      this.pinModel.form.private.value = false;
    }
    if (this.fromUrl) {
      this.pinModel.form.url.value = this.fromUrl.url;
      this.pinModel.form.referer.value = this.fromUrl.referer;
      this.pinModel.form.description.value = this.fromUrl.description;
    }
  },
  methods: {
    fetchTagList() {
      API.Tag.fetchList().then(
        (resp) => {
          this.tagOptions = resp.data;
        },
      );
    },
    getFilteredTags(text) {
      const filteredTagOptions = [];
      AutoComplete.getFilteredOptions(
        this.tagOptions,
        text,
      ).forEach(
        (option) => {
          filteredTagOptions.push(option.name);
        },
      );
      this.editorMeta.filteredTagOptions = filteredTagOptions;
    },
    fetchBoardList() {
      API.Board.fetchFullList(this.username).then(
        (resp) => {
          const boardOptions = [];
          resp.data.forEach(
            (board) => {
              const boardOption = { name: board.name, value: board.id };
              boardOptions.push(boardOption);
            },
          );
          this.boardOptions = boardOptions;
        },
        () => {
          console.log('Error occurs while fetch board full list');
        },
      );
    },
    onSelectBoard(boardIds) {
      this.boardIds = boardIds;
    },
    onUploadProcessing() {
      this.disableUrlField = true;
    },
    onUploadDone(imageId) {
      this.formUpload.imageId = imageId;
      this.checkDuplicates();
    },
    selectDuplicatePin(pin) {
      if (this.selectedDuplicatePin && this.selectedDuplicatePin.id === pin.id) {
        this.selectedDuplicatePin = null;
      } else {
        this.selectedDuplicatePin = pin;
      }
    },
    checkDuplicates() {
      const url = this.pinModel.form.url.value;
      const imageById = this.formUpload.imageId;
      if (!url && !imageById) {
        return;
      }
      API.Pin.checkDuplicates(url, imageById).then(
        (resp) => {
          if (resp.data.duplicates_found) {
            this.duplicatePins = resp.data.duplicates;
            if (this.duplicatePins.length > 0) {
              this.selectedDuplicatePin = this.duplicatePins[0];
            }
          } else {
            this.duplicatePins = [];
            this.selectedDuplicatePin = null;
          }
        },
      ).catch(() => {
        this.duplicatePins = [];
        this.selectedDuplicatePin = null;
      });
    },
    mergeWithSelected() {
      if (!this.selectedDuplicatePin) {
        return;
      }
      const loading = Loading.open(this);
      const self = this;
      const newTags = this.pinModel.form.tags.value || [];
      const targetPinId = this.selectedDuplicatePin.id;
      let tempPinId = null;
      let createPromise;
      if (isURLBlank(this.pinModel.form.url.value) && this.formUpload.imageId === null) {
        return;
      }
      if (this.formUpload.imageId === null) {
        const data = this.pinModel.asDataByFields(fields);
        data.force_create = true;
        createPromise = API.Pin.createFromURL(data);
      } else {
        const data = this.pinModel.asDataByFields(
          ['referer', 'description', 'tags', 'private'],
        );
        data.image_by_id = this.formUpload.imageId;
        data.force_create = true;
        createPromise = API.Pin.createFromUploaded(data);
      }
      createPromise.then((resp) => {
        tempPinId = resp.data.id;
        return API.Pin.mergePins(tempPinId, targetPinId);
      }).then((mergeResp) => {
        const promises = [];
        function done() {
          self.$emit('pinMerged', mergeResp.data.target_pin);
          self.$parent.close();
          loading.close();
        }
        bus.bus.$emit(bus.events.refreshPin);
        if (self.boardIds) {
          self.boardIds.forEach(
            (boardId) => {
              promises.push(API.Board.addToBoard(boardId, [targetPinId]));
            },
          );
        }
        if (promises.length > 0) {
          axios.all(promises).then(done);
        } else {
          done();
        }
      }).catch((error) => {
        console.log('Cannot merge pin:', error);
        loading.close();
      });
    },
    forceCreatePin() {
      this._createPin(true);
    },
    createPin() {
      this._createPin(false);
    },
    _createPin(force = false) {
      const loading = Loading.open(this);
      const self = this;
      let promise;
      if (isURLBlank(this.pinModel.form.url.value) && this.formUpload.imageId === null) {
        return;
      }
      if (this.formUpload.imageId === null) {
        const data = this.pinModel.asDataByFields(fields);
        if (force) {
          data.force_create = true;
        }
        promise = API.Pin.createFromURL(data);
      } else {
        const data = this.pinModel.asDataByFields(
          ['referer', 'description', 'tags', 'private'],
        );
        data.image_by_id = this.formUpload.imageId;
        if (force) {
          data.force_create = true;
        }
        promise = API.Pin.createFromUploaded(data);
      }
      promise.then(
        (resp) => {
          const promises = [];
          function done() {
            self.$emit('pinCreated', resp);
            self.$parent.close();
            loading.close();
          }
          bus.bus.$emit(bus.events.refreshPin);
          if (self.boardIds) {
            self.boardIds.forEach(
              (boardId) => {
                promises.push(API.Board.addToBoard(boardId, [resp.data.id]));
              },
            );
          }
          if (promises.length > 0) {
            axios.all(promises).then(done);
          } else {
            done();
          }
        },
      ).catch((error) => {
        if (error.response && error.response.status === 409 && error.response.data.duplicates_found) {
          this.duplicatePins = error.response.data.duplicates;
          if (this.duplicatePins.length > 0) {
            this.selectedDuplicatePin = this.duplicatePins[0];
          }
          loading.close();
        } else {
          console.log('Cannot create pin:', error);
          loading.close();
        }
      });
    },
    niceLinks,
  },
};
</script>

<style scoped>
.duplicate-warning {
  margin-top: 1rem;
}

.duplicate-pins-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.75rem;
  max-height: 300px;
  overflow-y: auto;
}

.duplicate-pin-item {
  display: flex;
  align-items: center;
  padding: 0.5rem;
  border: 2px solid #dbdbdb;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  background-color: #fff;
}

.duplicate-pin-item:hover {
  border-color: #3273dc;
  background-color: #f5f7fa;
}

.duplicate-pin-item.is-selected {
  border-color: #3273dc;
  background-color: #eef3fc;
}

.duplicate-pin-thumb {
  width: 60px;
  height: 60px;
  flex-shrink: 0;
  margin-right: 0.75rem;
}

.duplicate-pin-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 4px;
}

.duplicate-pin-info {
  flex: 1;
  min-width: 0;
}

.duplicate-pin-id {
  font-weight: bold;
  margin: 0 0 0.25rem 0;
  color: #363636;
}

.duplicate-pin-desc {
  margin: 0 0 0.25rem 0;
  font-size: 0.875rem;
  color: #7a7a7a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.duplicate-pin-tags {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
</style>
