<template>
  <div class="field is-grouped is-grouped-multiline mb-4">
    <p class="control">
      <span class="is-size-7 has-text-grey mr-2" style="line-height: 2.25;">
        {{ $t("errorTypeFilterLabel") }}:
      </span>
    </p>
    <p class="control" v-for="opt in options" :key="opt.key">
      <button
        class="button is-small"
        :class="{ 'is-info': value === opt.value }"
        @click="$emit('input', opt.value)"
      >
        <span>{{ $t(opt.labelKey) }}</span>
        <span
          v-if="opt.value === '' && totalCount > 0"
          class="tag is-dark is-light ml-1"
        >{{ totalCount }}</span>
        <span
          v-else-if="opt.value !== '' && getTypeCount(opt.value) > 0"
          class="tag is-dark is-light ml-1"
        >{{ getTypeCount(opt.value) }}</span>
      </button>
    </p>
  </div>
</template>

<script>
export default {
  name: 'LinkCheckFilterBar',
  props: {
    value: { type: String, default: '' },
    options: { type: Array, required: true },
    totalCount: { type: Number, default: 0 },
    typeStats: { type: Array, default: () => [] },
  },
  methods: {
    getTypeCount(t) {
      const stat = this.typeStats.find(s => s.error_type === t);
      return stat ? stat.count : 0;
    },
  },
};
</script>
