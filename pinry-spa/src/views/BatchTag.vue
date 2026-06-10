<template>
  <div class="batch-tag-view">
    <PHeader></PHeader>
    <BatchTagPanel></BatchTagPanel>
  </div>
</template>

<script>
import PHeader from '../components/PHeader.vue';
import BatchTagPanel from '../components/BatchTagPanel.vue';

export default {
  name: 'BatchTagView',
  components: {
    PHeader,
    BatchTagPanel,
  },
};
</script>

<style scoped lang="scss">
</style>
