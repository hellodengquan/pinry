<template>
  <div class="pins-for-tag">
    <PHeader></PHeader>
    <SearchPanel v-on:selected="doSearch"></SearchPanel>
    <div v-if="showMergeNotice" class="merge-notification">
      <span>{{ $t('tagMergeNotificationText', { oldTag: mergeOldTag, newTag: mergeNewTag }) }}</span>
    </div>
    <Pins
      v-if="pinFilters"
      :key="pinsKey"
      :pin-filters="pinFilters"
      :refresh-required="fullRefreshRequired"
    ></Pins>
    <Boards v-if="boardFilters" :filters="boardFilters"></Boards>
  </div>
</template>

<script>
import PHeader from '../components/PHeader.vue';
import Pins from '../components/Pins.vue';
import Boards from '../components/Boards.vue';
import SearchPanel from '../components/search/SearchPanel.vue';

export default {
  name: 'Search',
  data() {
    return {
      pinFilters: null,
      boardFilters: null,
      pinsKey: 0,
      fullRefreshRequired: false,
      showMergeNotice: false,
      mergeOldTag: '',
      mergeNewTag: '',
    };
  },
  components: {
    PHeader,
    Pins,
    Boards,
    SearchPanel,
  },
  created() {},
  methods: {
    doSearch(args) {
      const mergedFrom = args.mergedFrom;
      const isMergeSwitch = !!mergedFrom;

      this.pinFilters = null;
      this.boardFilters = null;

      if (isMergeSwitch) {
        this.fullRefreshRequired = true;
        this.showMergeNotice = true;
        this.mergeOldTag = mergedFrom;
        this.mergeNewTag = args.selected;
        setTimeout(() => {
          this.showMergeNotice = false;
        }, 3000);
      } else {
        this.fullRefreshRequired = false;
        this.showMergeNotice = false;
      }

      this.pinsKey += 1;

      this.$nextTick(() => {
        if (args.filterType === 'Tag') {
          this.pinFilters = {
            tagFilter: args.selected,
            isMergeSwitch,
            mergedFrom,
          };
        } else if (args.filterType === 'Board') {
          this.boardFilters = { boardNameContains: args.selected };
        }
      });
    },
  },
};
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped lang="scss">
.merge-notification {
  margin: 1rem 2rem;
  padding: 0.75rem 1rem;
  background-color: #fff3cd;
  border: 1px solid #ffeeba;
  border-radius: 4px;
  color: #856404;
  text-align: center;
  animation: fadeInOut 3s ease-in-out;

  span {
    font-size: 0.9rem;
  }

  @keyframes fadeInOut {
    0% {
      opacity: 0;
      transform: translateY(-10px);
    }
    10% {
      opacity: 1;
      transform: translateY(0);
    }
    80% {
      opacity: 1;
      transform: translateY(0);
    }
    100% {
      opacity: 0;
      transform: translateY(-10px);
    }
  }
}
</style>
