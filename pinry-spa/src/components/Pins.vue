<template>
  <div class="pins">
    <section class="section">
      <div class="batch-toolbar container" v-if="showBatchToolbar" style="margin-bottom: 1rem;">
        <div class="card">
          <div class="card-content" style="padding: 0.75rem 1rem;">
            <div class="level is-mobile">
              <div class="level-left">
                <div class="level-item">
                  <span class="tag is-info is-medium">
                    {{ $t("selectedPinsCount", { count: selectedPins.length }) }}
                  </span>
                </div>
                <div class="level-item" v-if="editorMeta.user.loggedIn">
                  <b-checkbox
                    v-model="selectAllChecked"
                    :indeterminate="isIndeterminate"
                    @input="toggleSelectAll">
                    {{ $t("selectAll") }}
                  </b-checkbox>
                </div>
              </div>
              <div class="level-right">
                <div class="level-item" v-if="editorMeta.user.loggedIn && pinFilters.boardFilter && isCurrentBoardOwner">
                  <b-button
                    type="is-primary"
                    size="is-small"
                    icon-left="mdi mdi-arrow-all"
                    :disabled="selectedPins.length === 0"
                    @click="openBatchMove">
                    {{ $t("batchMoveButton") }}
                  </b-button>
                </div>
                <div class="level-item" v-if="editorMeta.user.loggedIn">
                  <b-button
                    type="is-link"
                    size="is-small"
                    icon-left="mdi mdi-content-copy"
                    :disabled="selectedPins.length === 0"
                    @click="openBatchCopy">
                    {{ $t("batchCopyButton") }}
                  </b-button>
                </div>
                <div class="level-item" v-if="editorMeta.user.loggedIn">
                  <b-button
                    type="is-warning"
                    size="is-small"
                    icon-left="mdi mdi-eye-off-outline"
                    :disabled="selectedOwnedPins.length === 0"
                    @click="openBatchPrivacy">
                    {{ $t("batchPrivacyButton") }}
                  </b-button>
                </div>
                <div class="level-item" v-if="editorMeta.user.loggedIn">
                  <b-button
                    type="is-danger"
                    size="is-small"
                    icon-left="mdi mdi-delete"
                    :disabled="selectedOwnedPins.length === 0"
                    @click="openBatchDelete">
                    {{ $t("batchDeleteButton") }}
                  </b-button>
                </div>
                <div class="level-item">
                  <b-button
                    type="is-light"
                    size="is-small"
                    icon-left="mdi mdi-close"
                    @click="exitSelectMode">
                    {{ $t("exitSelectMode") }}
                  </b-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="select-mode-entry container" v-if="editorMeta.user.loggedIn && !selectMode" style="margin-bottom: 0.5rem;">
        <a @click="enterSelectMode" style="cursor: pointer; font-size: 0.85rem; color: #3273dc;">
          <span class="icon is-small"><i class="mdi mdi-check-all"></i></span>
          {{ $t("enterSelectMode") }}
        </a>
      </div>

      <div id="pins-container" class="container" v-if="blocks">
        <div
          v-masonry=""
          transition-duration="0.3s"
          item-selector=".grid-item"
          column-width=".grid-sizer"
          gutter=".gutter-sizer"
        >
          <template v-for="item in blocks">
            <div v-bind:key="item.id"
                 v-masonry-tile
                 :class="[item.class, { 'pin-selected': isPinSelected(item.id) }]"
                 class="grid pin-masonry">
              <div class="grid-sizer"></div>
              <div class="gutter-sizer"></div>
              <div class="pin-card grid-item">
                <div @mouseenter="showEditButtons(item.id)"
                     @mouseleave="hideEditButtons(item.id)"
                     :class="{ 'selectable-card': selectMode }"
                     @click.stop="selectMode ? togglePinSelection(item) : null">
                  <div v-if="selectMode" class="pin-select-checkbox" @click.stop="togglePinSelection(item)">
                    <b-checkbox
                      v-model="selectedIdsMap[item.id]"
                      :disabled="false"
                      :value="true">
                    </b-checkbox>
                  </div>
                  <EditorUI
                    v-show="!selectMode && shouldShowEdit(item.id)"
                    :pin="item"
                    :currentUsername="editorMeta.user.meta.username"
                    :currentBoard="editorMeta.currentBoard"
                    v-on:pin-delete-succeed="reset"
                    v-on:pin-remove-from-board-succeed="reset"
                  ></EditorUI>
                  <img :src="item.url"
                     @load="onPinImageLoaded(item.id)"
                     @click="selectMode ? null : openPreview(item)"
                     :alt="item.description"
                     :style="item.style"
                     class="pin-preview-image">
                </div>
                <div class="pin-footer">
                  <div class="description" v-show="item.description" v-html="niceLinks(item.description)"></div>
                  <div class="details">
                    <div class="is-pulled-left">
                      <img class="avatar" :src="item.avatar" alt="">
                    </div>
                    <div class="pin-info">
                      <span class="dim">{{ $t("pinnedByInfo") }}&nbsp;
                        <span>
                          <router-link
                            :to="{ name: 'user', params: {user: item.author} }">
                            {{ item.author }}
                          </router-link>
                        </span>
                        <template v-if="item.tags.length > 0">
                          &nbsp;in&nbsp;
                          <template v-for="tag in item.tags">
                            <span v-bind:key="tag" class="pin-tag">
                              <router-link :to="{ name: 'tag', params: {tag: tag} }"
                                           params="{tag: tag}">{{ tag }}</router-link>
                            </span>
                          </template>
                        </template>
                        <span v-if="item.referer">• <a :href="item.referer" target="_blank">{{ $t("sourceLink") }}</a></span>
                      </span>
                    </div>
                    <div class="is-clearfix"></div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
      <loadingSpinner v-bind:show="status.loading"></loadingSpinner>
      <noMore v-bind:show="!status.hasNext"></noMore>
    </section>
  </div>
</template>

<script>
import API from './api';
import pinHandler from './utils/PinHandler';
import PinPreview from './PinPreview.vue';
import loadingSpinner from './loadingSpinner.vue';
import noMore from './noMore.vue';
import scroll from './utils/scroll';
import bus from './utils/bus';
import EditorUI from './editors/PinEditorUI.vue';
import niceLinks from './utils/niceLinks';
import modals from './modals';

function createImageItem(pin) {
  const image = {};
  image.url = pinHandler.escapeUrl(pin.image.thumbnail.image);
  image.id = pin.id;
  image.owner_id = pin.submitter.id;
  image.private = pin.private;
  image.description = pin.description;
  image.tags = pin.tags;
  image.author = pin.submitter.username;
  image.avatar = `//gravatar.com/avatar/${pin.submitter.gravatar}`;
  image.large_image_url = pinHandler.escapeUrl(pin.image.image);
  image.original_image_url = pin.url;
  image.referer = pin.referer;
  image.orgianl_width = pin.image.width;
  image.style = {
    width: `${pin.image.thumbnail.width}px`,
    height: `${pin.image.thumbnail.height}px`,
  };
  image.class = {};
  return image;
}

function initialData() {
  return {
    blocks: [],
    blocksMap: {},
    status: {
      loading: false,
      hasNext: true,
      offset: 0,
    },
    editorMeta: {
      currentEditId: null,
      currentBoard: {},
      user: {
        loggedIn: false,
        meta: {},
      },
    },
    selectMode: false,
    selectedIdsMap: {},
  };
}

export default {
  name: 'pins',
  components: {
    loadingSpinner,
    noMore,
    EditorUI,
  },
  data() {
    return initialData();
  },
  props: {
    pinFilters: {
      type: Object,
      default() {
        return {
          tagFilter: null,
          userFilter: null,
          boardFilter: null,
        };
      },
    },
  },
  computed: {
    showBatchToolbar() {
      return this.selectMode && this.editorMeta.user.loggedIn;
    },
    selectedPins() {
      return this.blocks.filter(b => this.selectedIdsMap[b.id]);
    },
    selectedOwnedPins() {
      const { username } = this.editorMeta.user.meta;
      return this.selectedPins.filter(p => p.author === username);
    },
    selectablePins() {
      return this.blocks;
    },
    isCurrentBoardOwner() {
      if (!this.editorMeta.currentBoard || !this.editorMeta.currentBoard.submitter) {
        return false;
      }
      return this.editorMeta.currentBoard.submitter.username === this.editorMeta.user.meta.username;
    },
    selectAllChecked() {
      if (this.selectablePins.length === 0) return false;
      return this.selectablePins.every(p => this.selectedIdsMap[p.id]);
    },
    isIndeterminate() {
      const selectedCount = this.selectablePins.filter(p => this.selectedIdsMap[p.id]).length;
      return selectedCount > 0 && selectedCount < this.selectablePins.length;
    },
  },
  watch: {
    pinFilters() {
      this.reset();
    },
  },
  methods: {
    shouldShowEdit(id) {
      if (!this.editorMeta.user.loggedIn) {
        return false;
      }
      return this.editorMeta.currentEditId === id;
    },
    showEditButtons(id) {
      this.editorMeta.currentEditId = id;
    },
    hideEditButtons() {
      this.editorMeta.currentEditId = null;
    },
    onPinImageLoaded(itemId) {
      this.blocksMap[itemId].class = {
        'image-loaded': true,
      };
      this.blocksMap[itemId].style.height = 'auto';
    },
    registerScrollEvent() {
      const self = this;
      scroll.bindScroll2Bottom(
        () => {
          if (self.status.loading || !self.status.hasNext) {
            return;
          }
          self.fetchMore();
        },
      );
    },
    buildBlocks(results) {
      const blocks = [];
      results.forEach(
        (pin) => {
          const item = createImageItem(pin);
          blocks.push(
            item,
          );
        },
      );
      return blocks;
    },
    openPreview(pinItem) {
      this.$buefy.modal.open(
        {
          parent: this,
          component: PinPreview,
          props: {
            pinItem,
          },
          scroll: 'keep',
          customClass: 'pin-preview-at-home',
        },
      );
    },
    shouldFetchMore(created) {
      if (!created) {
        if (this.status.loading) {
          return false;
        }
        if (!this.status.hasNext) {
          return false;
        }
      }
      return true;
    },
    initialize() {
      this.initializeMeta();
      this.fetchMore(true);
    },
    initializeMeta() {
      const self = this;
      API.User.fetchUserInfo().then(
        (user) => {
          if (user === null) {
            self.editorMeta.user.loggedIn = false;
            self.editorMeta.user.meta = {};
          } else {
            self.editorMeta.user.meta = user;
            self.editorMeta.user.loggedIn = true;
          }
        },
      );
    },
    reset() {
      const data = initialData();
      Object.entries(data).forEach(
        (kv) => {
          const [key, value] = kv;
          this[key] = value;
        },
      );
      this.initialize();
    },
    fetchMore(created) {
      if (!this.shouldFetchMore(created)) {
        return;
      }
      this.status.loading = true;
      let promise;
      if (this.pinFilters.tagFilter) {
        promise = API.fetchPins(this.status.offset, this.pinFilters.tagFilter, null, null);
      } else if (this.pinFilters.userFilter) {
        promise = API.fetchPins(this.status.offset, null, this.pinFilters.userFilter, null);
      } else if (this.pinFilters.boardFilter) {
        const prevPromise = API.Board.get(this.pinFilters.boardFilter);
        promise = prevPromise.then(
          (resp) => {
            this.editorMeta.currentBoard = resp.data;
            return API.fetchPins(this.status.offset, null, null, this.pinFilters.boardFilter);
          },
        );
      } else if (this.pinFilters.idFilter) {
        promise = API.fetchPin(this.pinFilters.idFilter);
      } else {
        promise = API.fetchPins(this.status.offset);
      }
      promise.then(
        (resp) => {
          const { results, next } = resp.data;
          let newBlocks = this.buildBlocks(results);
          newBlocks.forEach(
            (item) => { this.blocksMap[item.id] = item; },
          );
          newBlocks = this.blocks.concat(newBlocks);
          this.blocks = newBlocks;
          this.status.offset = newBlocks.length;
          this.status.hasNext = !(next === null);
          this.status.loading = false;
        },
        () => { this.status.loading = false; },
      );
    },
    niceLinks,
    enterSelectMode() {
      this.selectMode = true;
    },
    exitSelectMode() {
      this.selectMode = false;
      this.selectedIdsMap = {};
    },
    isPinSelected(pinId) {
      return !!this.selectedIdsMap[pinId];
    },
    togglePinSelection(item) {
      this.$set(this.selectedIdsMap, item.id, !this.selectedIdsMap[item.id]);
    },
    toggleSelectAll(value) {
      if (value) {
        const newMap = {};
        this.selectablePins.forEach((p) => { newMap[p.id] = true; });
        this.selectedIdsMap = newMap;
      } else {
        this.selectedIdsMap = {};
      }
    },
    openBatchMove() {
      if (this.selectedPins.length === 0) return;
      modals.openBatchOperations(
        this,
        {
          operation: 'move',
          selectedPins: this.selectedPins,
          username: this.editorMeta.user.meta.username,
          currentBoardId: this.pinFilters.boardFilter ? Number(this.pinFilters.boardFilter) : null,
        },
        {
          'batch-move-succeed': succeededIds => this.onBatchMoveSucceed(succeededIds),
        },
      );
    },
    openBatchCopy() {
      if (this.selectedPins.length === 0) return;
      modals.openBatchOperations(
        this,
        {
          operation: 'copy',
          selectedPins: this.selectedPins,
          username: this.editorMeta.user.meta.username,
          currentBoardId: null,
        },
        {
          'batch-copy-succeed': () => {
            this.$buefy.toast.open(this.$t('batchCopySucceedToast'));
          },
        },
      );
    },
    openBatchDelete() {
      if (this.selectedOwnedPins.length === 0) return;
      modals.openBatchOperations(
        this,
        {
          operation: 'delete',
          selectedPins: this.selectedOwnedPins,
          username: this.editorMeta.user.meta.username,
          currentBoardId: null,
        },
        {
          'batch-delete-succeed': succeededIds => this.onBatchDeleteSucceed(succeededIds),
        },
      );
    },
    openBatchPrivacy() {
      if (this.selectedOwnedPins.length === 0) return;
      modals.openBatchOperations(
        this,
        {
          operation: 'privacy',
          selectedPins: this.selectedOwnedPins,
          username: this.editorMeta.user.meta.username,
          currentBoardId: null,
        },
        {
          'batch-privacy-succeed': () => {
            this.$buefy.toast.open(this.$t('batchPrivacySucceedToast'));
            this.reset();
          },
        },
      );
    },
    onBatchMoveSucceed(succeededIds) {
      if (this.pinFilters.boardFilter) {
        succeededIds.forEach((id) => {
          this.$delete(this.selectedIdsMap, id);
        });
        this.reset();
      }
    },
    onBatchDeleteSucceed(succeededIds) {
      succeededIds.forEach((id) => {
        this.$delete(this.selectedIdsMap, id);
      });
      this.reset();
    },
  },
  created() {
    bus.bus.$on(bus.events.refreshPin, this.reset);
    this.registerScrollEvent();
    this.initialize();
  },
};
</script>

<style lang="scss" scoped>
/* grid */
@import 'utils/pin';

.grid-sizer,
.grid-item { width: $pin-preview-width; }
.grid-item {
  margin-bottom: 15px;
}
.gutter-sizer {
  width: 15px;
}

/* pin-image transition */
.pin-masonry.image-loaded{
  opacity: 1;
  transition: opacity .3s;
}
.pin-masonry {
  opacity: 0;
}

/* selected state */
.pin-selected {
  .pin-card {
    box-shadow: 0 0 0 3px #3273dc;
    border-radius: 3px;
  }
}

.selectable-card {
  position: relative;
  cursor: pointer;
  &:hover {
    opacity: 0.9;
  }
}

.pin-select-checkbox {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 10;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 4px;
  padding: 4px 6px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.select-mode-entry {
  a {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    &:hover {
      text-decoration: underline;
    }
  }
}

.batch-toolbar {
  .card {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
  .level-item {
    margin-right: 0.5rem;
    &:last-child {
      margin-right: 0;
    }
  }
}

/* card */
$pin-footer-position-fix: -6px;
$avatar-width: 30px;
$avatar-height: 30px;
@import './utils/fonts';
@import './utils/loader.scss';

.pin-card{
  .pin-preview-image {
    cursor: zoom-in;
  }
  > img {
    min-width: $pin-preview-width;
    background-color: white;
    border-radius: 3px 3px 0 0;
    @include loader('../assets/loader.gif');
  }
  .avatar {
    height: $avatar-height;
    width: $avatar-width;
    border-radius: 3px;
  }
  .pin-tag {
    margin-right: 0.2rem;
  }
}
.pin-footer {
  position: relative;
  overflow-wrap: break-word;
  top: $pin-footer-position-fix;
  background-color: white;
  border-radius: 0 0 3px 3px ;
  box-shadow: 0 1px 0 #bbb;
  .description {
    @include description-font;
    padding: 8px;
    border-bottom: 1px solid #DDDDDD;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .details {
    @include secondary-font;
    padding: 10px;
    > .pin-info {
      line-height: 16px;
      width: 220px;
      padding-left: $avatar-width + 5px;
    }
    .pin-info a {
      font-weight: bold;
    }
  }
}

@import 'utils/grid-layout';
@include screen-grid-layout("#pins-container")

</style>
