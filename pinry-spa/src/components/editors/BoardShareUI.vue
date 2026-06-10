<template>
  <div class="board-share-modal">
    <div>
      <div class="modal-card" style="width: 600px; max-width: 90vw;">
        <header class="modal-card-head">
          <p class="modal-card-title">{{ $t("shareBoardTitle") }}</p>
        </header>
        <section class="modal-card-body">
          <div class="share-section">
            <div class="section-header">
              <h4 class="subtitle is-5">{{ $t("createShareLink") }}</h4>
            </div>
            <div class="field is-grouped">
              <div class="control is-expanded">
                <div class="select is-fullwidth">
                  <select v-model="expiresDays">
                    <option :value="null">{{ $t("neverExpires") }}</option>
                    <option :value="1">{{ $t("expiresIn1Day") }}</option>
                    <option :value="7">{{ $t("expiresIn7Days") }}</option>
                    <option :value="30">{{ $t("expiresIn30Days") }}</option>
                    <option :value="90">{{ $t("expiresIn90Days") }}</option>
                    <option :value="365">{{ $t("expiresIn1Year") }}</option>
                  </select>
                </div>
              </div>
              <div class="control">
                <button
                  class="button is-primary"
                  :class="{ 'is-loading': creating }"
                  :disabled="creating"
                  @click="createShareToken">
                  {{ $t("createLink") }}
                </button>
              </div>
            </div>
          </div>

          <div class="share-section">
            <div class="section-header">
              <h4 class="subtitle is-5">{{ $t("activeShareLinks") }}</h4>
              <span class="tag is-info is-light">{{ shareTokens.length }}</span>
            </div>

            <div v-if="loading" class="loading-container">
              <b-skeleton width="100%" height="80px"></b-skeleton>
            </div>

            <div v-else-if="shareTokens.length === 0" class="empty-state">
              <p class="has-text-grey">{{ $t("noShareLinks") }}</p>
            </div>

            <div v-else class="share-tokens-list">
              <div
                v-for="token in shareTokens"
                :key="token.id"
                class="share-token-card"
                :class="{ 'is-revoked': token.is_revoked, 'is-expired': !token.is_valid && !token.is_revoked }">
                <div class="token-status">
                  <span
                    v-if="token.is_revoked"
                    class="tag is-danger">
                    {{ $t("revoked") }}
                  </span>
                  <span
                    v-else-if="!token.is_valid"
                    class="tag is-warning">
                    {{ $t("expired") }}
                  </span>
                  <span
                    v-else
                    class="tag is-success">
                    {{ $t("active") }}
                  </span>
                </div>

                <div class="token-info">
                  <div class="token-url">
                    <code class="share-url">{{ token.share_url }}</code>
                    <button
                      class="button is-small is-light copy-btn"
                      @click="copyToClipboard(token.share_url)">
                      <b-icon icon="content-copy" size="is-small"></b-icon>
                    </button>
                  </div>
                  <div class="token-meta">
                    <span class="meta-item">
                      <span class="meta-label">{{ $t("createdAt") }}:</span>
                      <span class="meta-value">{{ formatDate(token.created_at) }}</span>
                    </span>
                    <span v-if="token.expires_at" class="meta-item">
                      <span class="meta-label">{{ $t("expiresAt") }}:</span>
                      <span class="meta-value">{{ formatDate(token.expires_at) }}</span>
                    </span>
                    <span class="meta-item">
                      <span class="meta-label">{{ $t("accessCount") }}:</span>
                      <span class="meta-value">{{ token.access_count }}</span>
                    </span>
                    <span v-if="token.last_accessed_at" class="meta-item">
                      <span class="meta-label">{{ $t("lastAccessed") }}:</span>
                      <span class="meta-value">{{ formatDate(token.last_accessed_at) }}</span>
                    </span>
                  </div>
                </div>

                <div class="token-actions">
                  <button
                    v-if="token.is_valid"
                    class="button is-small is-warning"
                    :class="{ 'is-loading': regeneratingId === token.id }"
                    :disabled="regeneratingId === token.id"
                    @click="regenerateToken(token)">
                    <b-icon icon="refresh" size="is-small"></b-icon>
                    &nbsp;{{ $t("regenerate") }}
                  </button>
                  <button
                    v-if="token.is_valid"
                    class="button is-small is-danger"
                    :class="{ 'is-loading': revokingId === token.id }"
                    :disabled="revokingId === token.id"
                    @click="revokeToken(token)">
                    <b-icon icon="cancel" size="is-small"></b-icon>
                    &nbsp;{{ $t("revoke") }}
                  </button>
                  <button
                    class="button is-small is-danger is-outlined"
                    @click="openShareLink(token.share_url)"
                    type="button">
                    <b-icon icon="open-in-new" size="is-small"></b-icon>
                    &nbsp;{{ $t("open") }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
        <footer class="modal-card-foot">
          <button class="button" type="button" @click="$parent.close()">{{ $t("closeButton") }}</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script>
import API from '../api';

export default {
  name: 'BoardShareUI',
  props: {
    board: {
      type: Object,
      required: true,
    },
  },
  data() {
    return {
      shareTokens: [],
      loading: false,
      creating: false,
      revokingId: null,
      regeneratingId: null,
      expiresDays: null,
    };
  },
  created() {
    this.loadShareTokens();
  },
  methods: {
    loadShareTokens() {
      this.loading = true;
      API.Board.listShareTokens(this.board.id).then(
        (resp) => {
          this.shareTokens = resp.data;
          this.loading = false;
        },
        (error) => {
          this.loading = false;
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('failedToLoadShareLinks'),
          });
          console.error('Failed to load share tokens:', error);
        },
      );
    },
    createShareToken() {
      this.creating = true;
      API.Board.createShareToken(this.board.id, this.expiresDays).then(
        (resp) => {
          this.creating = false;
          this.shareTokens.unshift(resp.data);
          this.$buefy.toast.open({
            type: 'is-success',
            message: this.$t('shareLinkCreated'),
          });
        },
        (error) => {
          this.creating = false;
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('failedToCreateShareLink'),
          });
          console.error('Failed to create share token:', error);
        },
      );
    },
    revokeToken(token) {
      this.$buefy.dialog.confirm({
        message: this.$t('confirmRevokeShareLink'),
        onConfirm: () => {
          this.revokingId = token.id;
          API.Board.revokeShareToken(this.board.id, token.id).then(
            (resp) => {
              this.revokingId = null;
              const idx = this.shareTokens.findIndex(t => t.id === token.id);
              if (idx !== -1) {
                this.shareTokens.splice(idx, 1, resp.data);
              }
              this.$buefy.toast.open({
                type: 'is-success',
                message: this.$t('shareLinkRevoked'),
              });
            },
            (error) => {
              this.revokingId = null;
              this.$buefy.toast.open({
                type: 'is-danger',
                message: this.$t('failedToRevokeShareLink'),
              });
              console.error('Failed to revoke share token:', error);
            },
          );
        },
      });
    },
    regenerateToken(token) {
      this.$buefy.dialog.confirm({
        message: this.$t('confirmRegenerateShareLink'),
        onConfirm: () => {
          this.regeneratingId = token.id;
          API.Board.regenerateShareToken(this.board.id, token.id, this.expiresDays).then(
            (resp) => {
              this.regeneratingId = null;
              const idx = this.shareTokens.findIndex(t => t.id === token.id);
              if (idx !== -1) {
                this.shareTokens.splice(idx, 1, resp.data);
              }
              this.$buefy.toast.open({
                type: 'is-success',
                message: this.$t('shareLinkRegenerated'),
              });
            },
            (error) => {
              this.regeneratingId = null;
              this.$buefy.toast.open({
                type: 'is-danger',
                message: this.$t('failedToRegenerateShareLink'),
              });
              console.error('Failed to regenerate share token:', error);
            },
          );
        },
      });
    },
    copyToClipboard(text) {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(
          () => {
            this.$buefy.toast.open({
              type: 'is-success',
              message: this.$t('linkCopiedToClipboard'),
            });
          },
        );
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        this.$buefy.toast.open({
          type: 'is-success',
          message: this.$t('linkCopiedToClipboard'),
        });
      }
    },
    openShareLink(url) {
      window.open(url, '_blank');
    },
    formatDate(dateStr) {
      if (!dateStr) return '-';
      const date = new Date(dateStr);
      return date.toLocaleString();
    },
  },
};
</script>

<style lang="scss" scoped>
.board-share-modal {
  .share-section {
    margin-bottom: 1.5rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid #eee;

    &:last-child {
      border-bottom: none;
      margin-bottom: 0;
      padding-bottom: 0;
    }

    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.75rem;
    }
  }

  .empty-state {
    padding: 2rem;
    text-align: center;
  }

  .loading-container {
    padding: 1rem;
  }

  .share-tokens-list {
    max-height: 400px;
    overflow-y: auto;
  }

  .share-token-card {
    padding: 1rem;
    margin-bottom: 0.75rem;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    background-color: #fafafa;
    transition: all 0.2s ease;

    &.is-revoked {
      opacity: 0.6;
      background-color: #fff5f5;
      border-color: #ffb3b3;
    }

    &.is-expired {
      opacity: 0.7;
      background-color: #fffbeb;
      border-color: #fde68a;
    }

    .token-status {
      margin-bottom: 0.5rem;
    }

    .token-info {
      margin-bottom: 0.75rem;

      .token-url {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.5rem;

        .share-url {
          flex: 1;
          padding: 0.3rem 0.5rem;
          background: #fff;
          border: 1px solid #ddd;
          border-radius: 4px;
          word-break: break-all;
          font-size: 0.8rem;
          max-height: 60px;
          overflow: hidden;
          text-overflow: ellipsis;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
        }

        .copy-btn {
          flex-shrink: 0;
        }
      }

      .token-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        font-size: 0.75rem;
        color: #666;

        .meta-item {
          display: flex;
          align-items: center;
          gap: 0.25rem;

          .meta-label {
            color: #999;
          }

          .meta-value {
            color: #555;
          }
        }
      }
    }

    .token-actions {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
  }
}
</style>
