<template>
  <div class="pins-for-share">
    <PHeader :is-share-mode="true" :share-board="boardInfo"></PHeader>

    <section v-if="boardInfo" class="section share-board-header">
      <div class="container">
        <div class="board-info-card">
          <div class="board-header-content">
            <div class="board-main-info">
              <h1 class="title is-3 board-name">{{ boardInfo.name }}</h1>
              <div class="board-meta">
                <span class="meta-item">
                  <b-icon icon="account" size="is-small"></b-icon>
                  &nbsp;{{ boardInfo.submitter_username }}
                </span>
                <span class="meta-item">
                  <b-icon icon="pin" size="is-small"></b-icon>
                  &nbsp;{{ boardInfo.total_pins }} {{ $t("pinsCount") }}
                </span>
                <span v-if="shareInfo" class="meta-item">
                  <b-icon icon="eye" size="is-small"></b-icon>
                  &nbsp;{{ shareInfo.access_count }} {{ $t("viewsCount") }}
                </span>
                <span v-if="shareInfo && shareInfo.expires_at" class="meta-item">
                  <b-icon icon="clock" size="is-small"></b-icon>
                  &nbsp;{{ $t("expiresAt") }}: {{ formatDate(shareInfo.expires_at) }}
                </span>
              </div>
            </div>
            <div class="share-badge">
              <span class="tag is-info is-medium">
                <b-icon icon="share-variant" size="is-small"></b-icon>
                &nbsp;{{ $t("sharedBoard") }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <Pins :pin-filters="filters" :is-share-mode="true" :share-token="shareToken"></Pins>
  </div>
</template>

<script>
import PHeader from '../components/PHeader.vue';
import Pins from '../components/Pins.vue';
import API from '../components/api';

export default {
  name: 'Pins4Share',
  data() {
    return {
      shareToken: null,
      boardInfo: null,
      shareInfo: null,
      filters: { shareTokenFilter: null },
      loading: false,
      error: null,
    };
  },
  components: {
    PHeader,
    Pins,
  },
  beforeRouteUpdate(to, from, next) {
    this.shareToken = to.params.token;
    this.filters = { shareTokenFilter: this.shareToken };
    this.loadShareData();
    next();
  },
  created() {
    this.initializeShare();
  },
  methods: {
    initializeShare() {
      this.shareToken = this.$route.params.token;
      this.filters = { shareTokenFilter: this.shareToken };
      this.loadShareData();
    },
    loadShareData() {
      this.loading = true;
      this.error = null;
      API.BoardShare.get(this.shareToken).then(
        (resp) => {
          this.boardInfo = resp.data.board;
          this.shareInfo = resp.data.share_info;
          this.loading = false;
        },
        (error) => {
          this.loading = false;
          if (error.response && error.response.status === 404) {
            this.error = error.response.data.detail || this.$t('shareLinkNotFound');
          } else {
            this.error = this.$t('failedToLoadShareData');
          }
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.error,
          });
        },
      );
    },
    formatDate(dateStr) {
      if (!dateStr) return '-';
      const date = new Date(dateStr);
      return date.toLocaleString();
    },
  },
};
</script>

<style scoped lang="scss">
.share-board-header {
  padding-top: 1.5rem;
  padding-bottom: 0.5rem;

  .board-info-card {
    background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
    border-radius: 12px;
    padding: 1.5rem 2rem;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);

    .board-header-content {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 1rem;
    }

    .board-main-info {
      flex: 1;
      min-width: 250px;
    }

    .board-name {
      margin-bottom: 0.75rem;
      color: #2c3e50;
      word-break: break-word;
    }

    .board-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 1.25rem;
      color: #6c757d;
      font-size: 0.9rem;

      .meta-item {
        display: flex;
        align-items: center;
      }
    }

    .share-badge {
      flex-shrink: 0;
    }
  }
}

@media (max-width: 768px) {
  .share-board-header {
    .board-info-card {
      padding: 1rem 1.25rem;

      .board-header-content {
        flex-direction: column;
      }

      .board-name {
        font-size: 1.5rem;
      }

      .board-meta {
        gap: 0.75rem;
        font-size: 0.85rem;
      }
    }
  }
}
</style>
