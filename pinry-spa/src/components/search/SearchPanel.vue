<template>
  <div class="search-panel">
    <div class="filter-selector">
      <div class="card-content">
        <b-field>
          <b-select v-bind:placeholder="$t('chooseFilterPlaceholder')" v-model="filterType">
            <option value="Tag">{{ $t("SearchPanelTagOption") }}</option>
            <option value="Board">{{ $t("SearchPanelBoardOption") }}</option>
          </b-select>
          <b-autocomplete
            v-show="filterType === 'Tag'"
            class="search-input"
            v-model="name"
            :data="filteredDataArray"
            :keep-first="true"
            :open-on-focus="true"
            v-bind:placeholder="$t('selectFilterPlaceholder')"
            icon="magnify"
            @select="option => selected = option">
            <template slot="empty">{{ $t("noResultsFound") }}</template>
          </b-autocomplete>
          <template v-if="filterType === 'Board'">
            <b-input
              class="search-input"
              type="search"
              v-model="boardText"
              v-bind:placeholder="$t('searchBoardPlaceholder')"
              icon="magnify"
            >
            </b-input>
            <p class="control">
              <b-button @click="searchBoard" class="button is-primary">{{ $t("searchButton") }}</b-button>
            </p>
          </template>
        </b-field>
      </div>
    </div>
  </div>
</template>

<script>
import api from '../api';
import bus from '../utils/bus';

export default {
  name: 'FilterSelector',
  data() {
    return {
      filterType: null,
      selectedOption: [],
      options: {
        Tag: [],
      },
      name: '',
      boardText: '',
      selected: null,
      currentSearchTag: null,
      pendingRefresh: false,
    };
  },
  methods: {
    selectOption(filterName) {
      this.name = '';
      this.boardText = '';
      if (filterName === 'Tag') {
        this.selectedOption = this.options.Tag;
      }
    },
    searchBoard() {
      if (this.boardText === '') {
        return;
      }
      this.$emit(
        'selected',
        { filterType: this.filterType, selected: this.boardText },
      );
    },
    fetchTagList() {
      const self = this;
      self.pendingRefresh = true;
      return api.Tag.fetchList().then(
        (resp) => {
          const options = [];
          resp.data.forEach(
            (tag) => {
              options.push(tag.name);
            },
          );
          self.options.Tag = options;
          if (self.filterType === 'Tag') {
            self.selectedOption = self.options.Tag;
          }
          self.pendingRefresh = false;
          self.handleTagListRefresh();
        },
      ).catch(() => {
        self.pendingRefresh = false;
      });
    },
    handleTagListRefresh() {
      if (this.currentSearchTag && this.filterType === 'Tag') {
        this.verifyAndReSearch();
      }
    },
    verifyAndReSearch() {
      const self = this;
      const tagToVerify = this.currentSearchTag;
      api.Tag.verify([tagToVerify]).then(
        (resp) => {
          const { invalid_tags } = resp.data;
          if (invalid_tags.length > 0) {
            const tagExists = self.options.Tag.some(
              (t) => t.toLowerCase() === tagToVerify.toLowerCase(),
            );
            if (!tagExists) {
              const closeMatch = self.options.Tag.find(
                (t) => t.toLowerCase().indexOf(tagToVerify.toLowerCase()) >= 0
                  || tagToVerify.toLowerCase().indexOf(t.toLowerCase()) >= 0,
              );
              if (closeMatch) {
                self.switchTagSearch(tagToVerify, closeMatch);
              } else {
                self.currentSearchTag = null;
              }
            }
          }
        },
      );
    },
    switchTagSearch(oldTag, newTag) {
      this.name = newTag;
      this.selected = newTag;
      this.currentSearchTag = newTag;
      this.$emit(
        'selected',
        {
          filterType: 'Tag',
          selected: newTag,
          mergedFrom: oldTag,
        },
      );
    },
    onTagSelected(tag) {
      this.currentSearchTag = tag;
      this.$emit(
        'selected',
        { filterType: this.filterType, selected: tag },
      );
    },
  },
  watch: {
    filterType(newVal) {
      this.selectOption(newVal);
    },
    selected(newVal) {
      if (newVal && this.filterType === 'Tag') {
        this.onTagSelected(newVal);
      }
    },
  },
  computed: {
    filteredDataArray() {
      return this.selectedOption.filter(
        (option) => {
          const ret = option
            .toString()
            .toLowerCase()
            .indexOf(this.name.toLowerCase()) >= 0;
          return ret;
        },
      );
    },
  },
  created() {
    this.fetchTagList();
    bus.bus.$on(bus.events.refreshTags, this.fetchTagList);
  },
  beforeDestroy() {
    bus.bus.$off(bus.events.refreshTags, this.fetchTagList);
  },
};
</script>

<style scoped="scoped" lang="scss">
  .search-panel {
    padding-top: 3rem;
    padding-left: 2rem;
    padding-right: 2rem;
  }
  .filter-selector {
    background-color: white;
    border-radius: 3px;
    .search-input {
      width: 100%;
    }
  }
</style>
