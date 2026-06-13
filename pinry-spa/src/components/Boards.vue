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

        <!-- 小量场景：沿用原有瀑布流 -->
        <template v-if="!useVirtualScroller">
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
                <div class="board-card grid-item" :class="{ 'is-selected': isSelected(item.id) }">
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
                </div>
              </div>
            </template>
          </div>
        </template>

        <!-- 大量场景：RecycleScroller 虚拟滚动 + 网格行 -->
        <RecycleScroller
          v-else
          class="virtual-scroller"
          :items="rows"
          :item-size="ROW_HEIGHT"
          key-field="rowIndex"
          v-observe-visibility
        >
          <template v-slot="{ item: row }">
            <div class="board-row" :style="{ height: ROW_HEIGHT + 'px' }">
              <div
                v-for="board in row.boards"
                :key="board.id"
                class="board-card virtual-board-card"
                :class="{ 'is-selected': isSelected(board.id) }"
                @mouseenter="currentEditBoard = board.id"
                @mouseleave="currentEditBoard = null"
              >
                <div v-if="showSelectionMode" class="select-checkbox" @click.stop="toggleSelect(board.id)">
                  <b-checkbox :value="isSelected(board.id)" disabled></b-checkbox>
                </div>
                <div class="card-image">
                  <BoardEditorUI
                    v-show="shouldShowEdit(board)"
                    :board="board"
                    v-on:board-delete-succeed="reset"
                    v-on:board-save-succeed="reset"
                  ></BoardEditorUI>
                  <router-link :to="{ name: 'board', params: { boardId: board.id } }">
                    <img
                      :src="board.preview_image_url"
                      @load="onPinImageLoaded(board.id)"
                      :style="{ width: CARD_WIDTH + 'px', height: CARD_WIDTH + 'px' }"
                      v-show="board.preview_image_url"
                      class="preview-image">
                  </router-link>
                </div>
                <div class="board-footer" @click.stop="toggleSelect(board.id)">
                  <p class="sub-title board-info">{{ board.name }}</p>
                  <p class="description">
                    <small>
                      {{ $t("pinsInBoard") }}<span class="num-pins">{{ board.total_pins }}</span>
                    </small>
                  </p>
                </div>
              </div>
            </div>
          </template>
        </RecycleScroller>
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

const CARD_WIDTH = 240;
const CARD_GAP = 15;
const FOOTER_HEIGHT = 72;
const CARD_HEIGHT = CARD_WIDTH + FOOTER_HEIGHT;
const ROW_HEIGHT = CARD_HEIGHT + CARD_GAP;
const VIRTUAL_MODE_THRESHOLD = 100;

function createBoardItem(board) {
  const defaultPreviewImage = placeholder;
  const boardItem = {};
  let previewImage = {
    image: { thumbnail: { image: null, width: CARD_WIDTH, height: CARD_WIDTH } },
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
    status: {
      loading: false,
      hasNext: true,
      offset: 0,
      nextCursor: null,
    },
    editorMeta: {
      user: { loggedIn: false, meta: { username: null } },
    },
    containerWidth: 1200,
    _io: null,
    _resizeHandler: null,
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
    useVirtualScroller() {
      return this.blocks.length >= VIRTUAL_MODE_THRESHOLD;
    },
    columnCount() {
      const gapTotal = Math.max(1, this.containerWidth / CARD_WIDTH);
      const cols = Math.floor((this.containerWidth + CARD_GAP) / (CARD_WIDTH + CARD_GAP));
      return Math.max(1, cols || 1);
    },
    rows() {
      if (!this.useVirtualScroller) return [];
      const cols = this.columnCount;
      const result = [];
      for (let i = 0; i < this.blocks.length; i += cols) {
        const chunk = this.blocks.slice(i, i + cols);
        result.push({
          rowIndex: Math.floor(i / cols),
          boards: chunk,
        });
      }
      return result;
    },
  },
  watch: {
    filters() {
      this.reset();
    },
  },
  methods: {
    initialize() {
      this.initializeMeta();
      this.measureContainer();
      this.fetchMore(true);
    },
    measureContainer() {
      this.$nextTick(() => {
        const el = document.getElementById('boards-container');
        if (el) {
          this.containerWidth = el.clientWidth || 1200;
        }
      });
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
      if (this._resizeHandler) {
        window.removeEventListener('resize', this._resizeHandler);
        this._resizeHandler = null;
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
    bindResize() {
      if (this._resizeHandler) return;
      this._resizeHandler = () => this.measureContainer();
      window.addEventListener('resize', this._resizeHandler);
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
          this.$nextTick(() => this.measureContainer());
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
    if (this._resizeHandler) {
      window.removeEventListener('resize', this._resizeHandler);
      this._resizeHandler = null;
    }
  },
  created() {
    bus.bus.$on(bus.events.refreshBoards, this.reset);
    this.registerScrollEvent();
    this.bindResize();
    this.initialize();
  },
  mounted() {
    this.measureContainer();
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

.virtual-scroller {
  width: 100%;
  overflow: visible;
}

.board-row {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 15px;
  align-items: flex-start;
  width: 100%;
  .virtual-board-card {
    flex: 0 0 240px;
  }
}

.board-card{
  position: relative;
  width: 240px;
  &.is-selected {
    box-shadow: 0 0 0 2px #3273dc;
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
    min-width: 240px;
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
  min-height: 72px;
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
