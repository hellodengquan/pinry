<template>
  <div class="boards">
    <section class="section">
      <div v-if="showSelectionBar" class="selection-bar">
        <div class="selection-info">
          <span>{{ $t("selectedCount", { count: selectedIds.length }) }}</span>
        </div>
        <div class="selection-actions">
          <button class="button is-small" @click="toggleSelectAll">
            {{ isAllSelected ? $t("clearSelection") : $t("selectAll") }}
          </button>
          <button
            v-if="!filters.showArchived"
            class="button is-small is-primary"
            @click="confirmBulkArchive"
            :disabled="selectedIds.length === 0"
          >
            <b-icon icon="archive" custom-size="mdi-18px"></b-icon>
            <span>{{ $t("bulkArchive") }}</span>
          </button>
          <button
            v-else
            class="button is-small is-primary"
            @click="confirmBulkUnarchive"
            :disabled="selectedIds.length === 0"
          >
            <b-icon icon="unarchive" custom-size="mdi-18px"></b-icon>
            <span>{{ $t("bulkUnarchive") }}</span>
          </button>
        </div>
      </div>

      <div id="boards-container" class="container" v-if="blocks">
        <div
          v-masonry=""          transition-duration="0.3s"
          item-selector=".grid-item"
          column-width=".grid-sizer"
          gutter=".gutter-sizer"
        >
          <template v-for="item in blocks">
            <div v-bind:key="item.id"
                 v-masonry-tile
                 :class="item.class"
                 class="grid">
              <div class="grid-sizer"></div>
              <div class="gutter-sizer"></div>
              <div
                class="board-card grid-item"
                :class="{ 'is-selected': isSelected(item.id) }"
                :data-board-id="item.id"
                ref="boardCardRef"
              >
                <template v-if="isItemVisible(item.id)">
                  <div @mouseenter="currentEditBoard = item.id"
                       @mouseleave="currentEditBoard = null"
                  >
                    <div v-if="showSelectionMode" class="select-checkbox" @click.stop="toggleSelect(item.id)">
                      <b-checkbox :value="isSelected(item.id)" disabled></b-checkbox>
                    </div>
                    <div class="card-image">
                      <BoardEditorUI
                        v-show="shouldShowEdit(item)"
                        :board="item"
                        v-on:board-delete-succeed="reset"
                        v-on:board-save-succeed="reset"
                      ></BoardEditorUI>
                      <router-link :to="{ name: 'board', params: { boardId: item.id } }">
                        <img :src="item.preview_image_url"
                           @load="onPinImageLoaded(item.id)"
                           :style="item.style"
                           v-show="item.preview_image_url"
                           class="preview-image">
                      </router-link>
                    </div>
                    <div class="board-footer" @click.stop="toggleSelect(item.id)">
                      <p class="sub-title board-info">{{ item.name }}</p>
                      <p class="description">
                        <small>
                          {{ $t("pinsInBoard") }}<span class="num-pins">{{ item.total_pins }}</span>
                        </small>
                      </p>
                    </div>
                  </div>
                </template>
                <template v-else>
                  <div class="board-card-placeholder" :style="getPlaceholderStyle(item)"></div>
                </template>
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
import loadingSpinner from './loadingSpinner.vue';
import noMore from './noMore.vue';
import scroll from './utils/scroll';
import placeholder from '../assets/pinry-placeholder.jpg';
import BoardEditorUI from './editors/BoardEditUI.vue';
import bus from './utils/bus';

const VIRTUAL_THRESHOLD = 200;
const BOARD_FOOTER_ESTIMATED_HEIGHT = 72;

function createBoardItem(board) {
  const defaultPreviewImage = placeholder;
  const boardItem = {};
  let previewImage = {
    image: { thumbnail: { image: null, width: 240, height: 240 } },
  };
  if (board.cover !== null) {
    previewImage = board.cover;
  }
  boardItem.id = board.id;
  boardItem.name = board.name;
  boardItem.private = board.private;
  boardItem.is_archived = board.is_archived;
  boardItem.total_pins = board.total_pins;
  if (previewImage.image.thumbnail.image !== null) {
    boardItem.preview_image_url = pinHandler.escapeUrl(
      previewImage.image.thumbnail.image,
    );
  } else {
    boardItem.preview_image_url = defaultPreviewImage;
  }
  boardItem.thumbWidth = previewImage.image.thumbnail.width;
  boardItem.thumbHeight = previewImage.image.thumbnail.height;
  boardItem.style = {
    width: `${previewImage.image.thumbnail.width}px`,
    height: `${previewImage.image.thumbnail.height}px`,
  };
  boardItem.class = {};
  boardItem.author = board.submitter.username;
  return boardItem;
}

function initialData() {
  return {
    currentEditBoard: null,
    blocks: [],
    blocksMap: {},
    selectedIds: [],
    visibleIds: new Set(),
    status: {
      loading: false,
      hasNext: true,
      offset: 0,
      nextCursor: null,
    },
    editorMeta: {
      user: { loggedIn: false, meta: { username: null } },
    },
    _io: null,
  };
}

export default {
  name: 'boards',
  components: {
    loadingSpinner,
    noMore,
    BoardEditorUI,
  },
  data: initialData,
  props: ['filters'],
  computed: {
    isCurrentUserBoardOwner() {
      if (!this.editorMeta.user.loggedIn) return false;
      if (!this.filters || !this.filters.boardUsername) return false;
      return this.editorMeta.user.meta.username === this.filters.boardUsername;
    },
    showSelectionMode() {
      return this.isCurrentUserBoardOwner;
    },
    showSelectionBar() {
      return this.showSelectionMode;
    },
    isAllSelected() {
      if (this.blocks.length === 0) return false;
      return this.blocks.every(b => this.selectedIds.includes(b.id));
    },
  },
  watch: {
    filters() {
      this.reset();
    },
    blocks() {
      this.$nextTick(() => { this.bindIntersectionObserver(); });
    },
  },
  methods: {
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
      if (this._io) {
        this._io.disconnect();
        this._io = null;
      }
      const data = initialData();
      Object.entries(data).forEach(
        (kv) => {
          const [key, value] = kv;
          this[key] = value;
        },
      );
      this.initialize();
    },
    bindIntersectionObserver() {
      if (typeof window === 'undefined' || !('IntersectionObserver' in window)) {
        this.blocks.forEach((b) => { this.visibleIds.add(b.id); });
        return;
      }
      if (!this._io) {
        const self = this;
        const rootMargin = `${VIRTUAL_THRESHOLD}px 0px ${VIRTUAL_THRESHOLD}px 0px`;
        this._io = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              const idAttr = entry.target.getAttribute('data-board-id');
              if (!idAttr) return;
              const id = parseInt(idAttr, 10);
              if (entry.isIntersecting) {
                self.visibleIds.add(id);
              } else {
                self.visibleIds.delete(id);
              }
            });
            self.$forceUpdate();
          },
          { rootMargin, threshold: 0 },
        );
      }
      const cards = this.$refs.boardCardRef || [];
      (Array.isArray(cards) ? cards : [cards]).forEach((el) => {
        if (el && el.$el) this._io.observe(el.$el);
        else if (el) this._io.observe(el);
      });
    },
    isItemVisible(id) {
      if (!this._io) return true;
      return this.visibleIds.has(id);
    },
    getPlaceholderStyle(item) {
      const height = (item.thumbHeight || 240) + BOARD_FOOTER_ESTIMATED_HEIGHT;
      return {
        width: `${item.thumbWidth || 240}px`,
        height: `${height}px`,
      };
    },
    shouldShowEdit(board) {
      if (!this.editorMeta.user.loggedIn) {
        return false;
      }
      if (this.editorMeta.user.meta.username !== board.author) {
        return false;
      }
      return this.currentEditBoard === board.id;
    },
    isSelected(id) {
      return this.selectedIds.includes(id);
    },
    toggleSelect(id) {
      if (!this.showSelectionMode) return;
      const idx = this.selectedIds.indexOf(id);
      if (idx >= 0) {
        this.selectedIds.splice(idx, 1);
      } else {
        this.selectedIds.push(id);
      }
    },
    toggleSelectAll() {
      if (this.isAllSelected) {
        this.selectedIds = [];
      } else {
        this.selectedIds = this.blocks.map(b => b.id);
      }
    },
    confirmBulkArchive() {
      const self = this;
      const count = this.selectedIds.length;
      if (count === 0) return;
      this.$buefy.dialog.confirm({
        message: this.$t('bulkArchiveConfirm', { count }),
        onConfirm: () => {
          API.Board.bulkArchive(self.selectedIds).then(
            (resp) => {
              self.$buefy.toast.open(
                self.$t('bulkArchiveSuccess', { count: resp.data.updated_count }),
              );
              self.reset();
            },
            () => {
              self.$buefy.toast.open(
                { type: 'is-danger', message: self.$t('bulkOperationFailed') },
              );
            },
          );
        },
      });
    },
    confirmBulkUnarchive() {
      const self = this;
      const count = this.selectedIds.length;
      if (count === 0) return;
      this.$buefy.dialog.confirm({
        message: this.$t('bulkUnarchiveConfirm', { count }),
        onConfirm: () => {
          API.Board.bulkUnarchive(self.selectedIds).then(
            (resp) => {
              self.$buefy.toast.open(
                self.$t('bulkUnarchiveSuccess', { count: resp.data.updated_count }),
              );
              self.reset();
            },
            () => {
              self.$buefy.toast.open(
                { type: 'is-danger', message: self.$t('bulkOperationFailed') },
              );
            },
          );
        },
      });
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
          const item = createBoardItem(pin);
          blocks.push(
            item,
          );
        },
      );
      return blocks;
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
    fetchMore(created) {
      if (!this.shouldFetchMore(created)) {
        return;
      }
      let promise;
      let useCursor = false;
      if (this.filters.boardUsername && this.filters.showArchived) {
        promise = API.fetchArchivedBoardForUser(
          this.filters.boardUsername,
          this.status.nextCursor,
        );
        useCursor = true;
      } else if (this.filters.boardUsername) {
        promise = API.fetchBoardForUser(
          this.filters.boardUsername,
          this.status.offset,
        );
      } else if (this.filters.boardNameContains) {
        promise = API.Board.fetchListWhichContains(
          this.filters.boardNameContains,
          this.status.offset,
        );
      } else {
        return;
      }
      this.status.loading = true;
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
          if (useCursor) {
            if (next) {
              const url = new URL(next);
              this.status.nextCursor = url.searchParams.get('cursor') || null;
            } else {
              this.status.nextCursor = null;
            }
          }
          this.status.hasNext = !(next === null);
          this.status.loading = false;
        },
        () => { this.status.loading = false; },
      );
    },
  },
  beforeDestroy() {
    if (this._io) {
      this._io.disconnect();
      this._io = null;
    }
  },
  created() {
    bus.bus.$on(bus.events.refreshBoards, this.reset);
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

/* card */
$pin-footer-position-fix: -6px;
$avatar-width: 30px;
$avatar-height: 30px;
@import './utils/fonts';
@import './utils/loader.scss';

.selection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin-bottom: 16px;
  background-color: #f5f5f5;
  border-radius: 4px;
  border: 1px solid #dbdbdb;
  .selection-info {
    font-weight: bold;
    color: #363636;
  }
  .selection-actions {
    display: flex;
    gap: 8px;
    .button {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
  }
}

.board-card{
  position: relative;
  &.is-selected {
    box-shadow: 0 0 0 2px #3273dc;
    border-radius: 3px;
  }
  .board-card-placeholder {
    background-color: #fafafa;
    border-radius: 3px;
  }
  .select-checkbox {
    position: absolute;
    top: 8px;
    left: 8px;
    z-index: 10;
    background: rgba(255,255,255,0.9);
    padding: 4px;
    border-radius: 3px;
  }
  .card-image > img {
    min-width: $pin-preview-width;
    background-color: white;
    border-radius: 3px 3px 0 0;
    @include loader('../assets/loader.gif');
  }
}
.board-footer {
  position: relative;
  top: $pin-footer-position-fix;
  background-color: white;
  border-radius: 0 0 3px 3px ;
  box-shadow: 0 1px 0 #bbb;
  font-weight: bold;
  cursor: pointer;
  .description {
    @include secondary-font;
    padding-left: 10px;
    padding-bottom: 5px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .board-info {
    padding: 10px;
    color: $main-title-font-color;
  }
  .num-pins {
    font-size: 0.8rem;
    color: $main-title-font-color;
  }
}

@import 'utils/grid-layout';
@include screen-grid-layout("#boards-container")

</style>
