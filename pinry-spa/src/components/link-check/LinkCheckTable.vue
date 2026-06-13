<template>
  <div>
    <div v-if="loading" class="has-text-centered py-6">
      <i class="fa fa-spinner fa-spin is-size-3"></i>
    </div>
    <div v-else-if="items.length === 0" class="notification is-success is-light has-text-centered py-6">
      <i class="fa fa-check-circle is-size-3 mr-2"></i>
      {{ emptyText || $t("linkCheckEmptyTodo") }}
    </div>
    <div v-else class="checks-list">
      <div
        v-for="item in items"
        :key="prefix + item.id"
        class="card check-card"
      >
        <div class="card-content">
          <div class="columns">
            <div class="column is-2">
              <figure class="image is-4by3">
                <img
                  v-if="item.pin_detail && item.pin_detail.image && item.pin_detail.image.square"
                  :src="item.pin_detail.image.square.image"
                  alt="pin thumbnail"
                >
              </figure>
            </div>
            <div class="column is-10">
              <div class="is-flex is-justify-content-space-between is-align-items-flex-start">
                <div>
                  <p class="is-size-5 has-text-weight-semibold">
                    <router-link
                      v-if="item.pin_detail"
                      :to="{ name: 'pin', params: { pinId: item.pin } }"
                    >
                      Pin #{{ item.pin }}
                    </router-link>
                    <span v-else>Pin #{{ item.pin }}</span>
                    <span
                      class="tag ml-2"
                      :class="statusTagClass(item.status)"
                    >{{ statusLabel(item.status) }}</span>
                    <span
                      v-if="item.error_type"
                      class="tag ml-1"
                      :class="errorTypeTagClass(item.error_type)"
                    >{{ errorTypeLabel(item.error_type) }}</span>
                    <span
                      class="tag ml-1"
                      :class="actionTagClass(item.action_status)"
                    >{{ actionLabel(item.action_status) }}</span>
                  </p>
                  <p class="is-size-7 has-text-grey mt-1">
                    <span class="mr-3">{{ $t("linkCheckHttpStatus") }}: <strong>{{ item.http_status_code || 'N/A' }}</strong></span>
                    <span class="mr-3">{{ $t("linkCheckResponseTime") }}: <strong>{{ item.response_time_ms || 'N/A' }}</strong></span>
                    <span>{{ $t("linkCheckCheckedAt") }}: <strong>{{ formatDate(item.checked_at) }}</strong></span>
                  </p>
                  <p class="is-size-6 mt-2 break-all">
                    <a :href="item.url" target="_blank" rel="noopener noreferrer">
                      <i class="fa fa-external-link mr-1"></i>{{ item.url }}
                    </a>
                  </p>
                  <p v-if="item.error_message" class="is-size-6 has-text-danger mt-2">
                    <i class="fa fa-exclamation-triangle mr-1"></i>
                    <strong>{{ $t("linkCheckErrorMessage") }}:</strong> {{ item.error_message }}
                  </p>
                  <p v-if="item.action_note" class="is-size-6 has-text-info mt-2">
                    <i class="fa fa-sticky-note mr-1"></i>
                    <strong>Note:</strong> {{ item.action_note }}
                  </p>
                  <p v-if="item.pin_detail && item.pin_detail.description" class="is-size-6 mt-2">
                    {{ item.pin_detail.description }}
                  </p>
                </div>
              </div>
              <div
                v-if="showActions(item)"
                class="field is-grouped is-grouped-multiline mt-4"
              >
                <p class="control">
                  <button class="button is-small is-warning" @click="$emit('open-source', item)">
                    <i class="fa fa-external-link mr-1"></i>{{ $t("linkCheckSourceLink") }}
                  </button>
                </p>
                <p class="control">
                  <button
                    class="button is-small is-info"
                    :class="{ 'is-loading': recheckingId === item.id }"
                    :disabled="recheckingId === item.id"
                    @click="$emit('recheck', item)"
                  >
                    <i class="fa fa-refresh mr-1"></i>{{ $t("linkCheckActionButtonRecheck") }}
                  </button>
                </p>
                <p class="control">
                  <button class="button is-small" @click="$emit('action', item, 'ignore')">
                    <i class="fa fa-eye-slash mr-1"></i>{{ $t("linkCheckActionButtonIgnore") }}
                  </button>
                </p>
                <p class="control">
                  <button class="button is-small is-success" @click="$emit('action', item, 'fixed')">
                    <i class="fa fa-wrench mr-1"></i>{{ $t("linkCheckActionButtonFixed") }}
                  </button>
                </p>
                <p v-if="item.action_status === 'unhandled'" class="control">
                  <button class="button is-small is-primary" @click="$emit('action', item, 'handled')">
                    <i class="fa fa-check mr-1"></i>{{ $t("linkCheckActionButtonHandled") }}
                  </button>
                </p>
                <p class="control">
                  <button class="button is-small is-danger" @click="$emit('confirm-delete', item)">
                    <i class="fa fa-trash mr-1"></i>{{ $t("linkCheckActionButtonDelete") }}
                  </button>
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'LinkCheckTable',
  props: {
    items: { type: Array, required: true },
    loading: { type: Boolean, default: false },
    emptyText: { type: String, default: '' },
    prefix: { type: String, default: 'item-' },
    recheckingId: { type: Number, default: null },
    showAllActions: { type: Boolean, default: false },
  },
  methods: {
    showActions(item) {
      if (this.showAllActions) {
        return item.status === 'failed' && item.action_status === 'unhandled';
      }
      return item.status === 'failed';
    },
    formatDate(dt) {
      if (!dt) return '—';
      const d = new Date(dt);
      if (isNaN(d.getTime())) return dt;
      return d.toLocaleString();
    },
    statusLabel(s) {
      const map = {
        pending: this.$t("linkCheckStatusPending"),
        running: this.$t("linkCheckStatusRunning"),
        success: this.$t("linkCheckStatusSuccess"),
        failed: this.$t("linkCheckStatusFailed"),
      };
      return map[s] || s;
    },
    statusTagClass(s) {
      const map = {
        pending: 'is-warning is-light',
        running: 'is-info is-light',
        success: 'is-success is-light',
        failed: 'is-danger is-light',
      };
      return map[s] || 'is-light';
    },
    actionLabel(a) {
      const map = {
        unhandled: this.$t("linkCheckActionUnhandled"),
        ignored: this.$t("linkCheckActionIgnored"),
        fixed: this.$t("linkCheckActionFixed"),
        deleted: this.$t("linkCheckActionDeleted"),
        handled: this.$t("linkCheckActionHandled"),
      };
      return map[a] || a;
    },
    actionTagClass(a) {
      const map = {
        unhandled: 'is-warning is-light',
        ignored: 'is-dark is-light',
        fixed: 'is-success is-light',
        deleted: 'is-danger is-light',
        handled: 'is-primary is-light',
      };
      return map[a] || 'is-light';
    },
    errorTypeLabel(t) {
      if (!t) return '';
      const map = {
        connection_refused: this.$t("errorTypeConnectionRefused"),
        dns_error: this.$t("errorTypeDnsError"),
        timeout: this.$t("errorTypeTimeout"),
        too_many_redirects: this.$t("errorTypeTooManyRedirects"),
        ssl_error: this.$t("errorTypeSslError"),
        http_4xx: this.$t("errorTypeHttp4xx"),
        http_5xx: this.$t("errorTypeHttp5xx"),
        unknown: this.$t("errorTypeUnknown"),
      };
      return map[t] || t;
    },
    errorTypeTagClass(t) {
      if (!t) return 'is-light';
      const map = {
        connection_refused: 'is-danger is-light',
        dns_error: 'is-warning is-light',
        timeout: 'is-info is-light',
        too_many_redirects: 'is-link is-light',
        ssl_error: 'is-danger is-light',
        http_4xx: 'is-warning is-light',
        http_5xx: 'is-danger is-light',
        unknown: 'is-light',
      };
      return map[t] || 'is-light';
    },
  },
};
</script>

<style scoped lang="scss">
.check-card {
  margin-bottom: 1rem;
  transition: box-shadow 0.2s;
  &:hover {
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  }
}
.break-all {
  word-break: break-all;
}
</style>
