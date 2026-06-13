<template>
  <nav v-if="totalPages > 1" class="pagination is-centered is-small" role="navigation">
    <button
      class="pagination-previous"
      :disabled="currentPage <= 1"
      @click="$emit('page-change', currentPage - 1)"
    >
      <i class="fa fa-chevron-left"></i>
    </button>
    <button
      class="pagination-next"
      :disabled="currentPage >= totalPages"
      @click="$emit('page-change', currentPage + 1)"
    >
      <i class="fa fa-chevron-right"></i>
    </button>
    <ul class="pagination-list">
      <li v-if="currentPage > 2">
        <button class="pagination-link" @click="$emit('page-change', 1)">1</button>
      </li>
      <li v-if="currentPage > 3">
        <span class="pagination-ellipsis">&hellip;</span>
      </li>
      <li v-if="currentPage > 1">
        <button class="pagination-link" @click="$emit('page-change', currentPage - 1)">
          {{ currentPage - 1 }}
        </button>
      </li>
      <li>
        <button class="pagination-link is-current">{{ currentPage }}</button>
      </li>
      <li v-if="currentPage < totalPages">
        <button class="pagination-link" @click="$emit('page-change', currentPage + 1)">
          {{ currentPage + 1 }}
        </button>
      </li>
      <li v-if="currentPage < totalPages - 2">
        <span class="pagination-ellipsis">&hellip;</span>
      </li>
      <li v-if="currentPage < totalPages - 1">
        <button class="pagination-link" @click="$emit('page-change', totalPages)">
          {{ totalPages }}
        </button>
      </li>
    </ul>
    <p class="is-size-7 has-text-grey ml-3">
      {{ totalCount }} {{ $t("linkCheckTotalPins").replace(':', '') }}
    </p>
  </nav>
</template>

<script>
export default {
  name: 'LinkCheckPagination',
  props: {
    totalCount: { type: Number, default: 0 },
    currentPage: { type: Number, default: 1 },
    pageSize: { type: Number, default: 20 },
  },
  computed: {
    totalPages() {
      return Math.max(1, Math.ceil(this.totalCount / this.pageSize));
    },
  },
};
</script>
