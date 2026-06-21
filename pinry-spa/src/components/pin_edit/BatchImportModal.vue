<template>
  <div class="batch-import-modal">
    <div>
      <div class="modal-card" style="width: 900px">
        <header class="modal-card-head">
          <p class="modal-card-title">{{ $t("batchImportTitle") }}</p>
        </header>
        <section class="modal-card-body">
          <div v-if="step === 'input'">
            <b-field :label="$t('batchImportUrlListLabel')">
              <b-input
                type="textarea"
                v-model="urlText"
                :placeholder="$t('batchImportUrlListPlaceholder')"
                rows="8"
              ></b-input>
            </b-field>
            <div class="columns">
              <div class="column">
                <FilterSelect
                  :allOptions="boardOptions"
                  v-on:selected="onSelectBoard"
                ></FilterSelect>
              </div>
              <div class="column">
                <b-field :label="$t('tagsLabel')">
                  <b-taginput
                    v-model="defaultTags"
                    :data="filteredTagOptions"
                    autocomplete
                    ellipsis
                    icon="label"
                    :allow-new="true"
                    :placeholder="$t('pinCreateModalImageTagsPlaceholder')"
                    @typing="getFilteredTags">
                  </b-taginput>
                </b-field>
                <b-field :label="$t('privacyOptionLabel')">
                  <b-checkbox v-model="defaultPrivate">
                    {{ $t("isPrivateCheckbox") }}
                  </b-checkbox>
                </b-field>
              </div>
            </div>
          </div>

          <div v-if="step === 'prechecking'">
            <div class="has-text-centered">
              <b-progress type="is-primary" :value="precheckProgress" show-value>{{ precheckProgress }}%</b-progress>
              <p class="mt-4">{{ $t("batchImportPrechecking") }}</p>
            </div>
          </div>

          <div v-if="step === 'result'">
            <div class="box">
              <div class="columns is-multiline">
                <div class="column is-3">
                  <div class="has-text-centered">
                    <p class="heading">{{ $t("batchImportTotal") }}</p>
                    <p class="title is-4">{{ summary.total }}</p>
                  </div>
                </div>
                <div class="column is-3">
                  <div class="has-text-centered">
                    <p class="heading">{{ $t("batchImportCanImport") }}</p>
                    <p class="title is-4 has-text-success">{{ summary.can_import }}</p>
                  </div>
                </div>
                <div class="column is-3">
                  <div class="has-text-centered">
                    <p class="heading">{{ $t("batchImportHasIssues") }}</p>
                    <p class="title is-4 has-text-danger">{{ summary.has_issues }}</p>
                  </div>
                </div>
                <div class="column is-3">
                  <div class="has-text-centered">
                    <p class="heading">{{ $t("batchImportHasWarnings") }}</p>
                    <p class="title is-4 has-text-warning">{{ summary.has_warnings }}</p>
                  </div>
                </div>
              </div>
            </div>

            <div class="mb-3">
              <b-checkbox v-model="selectAllCanImport" @change="toggleSelectAll">
                {{ $t("batchImportSelectAllCanImport") }}
              </b-checkbox>
              <b-checkbox v-model="includeWithWarnings" @change="applyIncludeWarnings">
                {{ $t("batchImportIncludeWarnings") }}
              </b-checkbox>
            </div>

            <div style="max-height: 400px; overflow-y: auto;">
              <table class="table is-fullwidth is-striped">
                <thead>
                  <tr>
                    <th style="width: 40px"></th>
                    <th style="width: 50px">#</th>
                    <th>{{ $t("imageUrlLabel") }}</th>
                    <th style="width: 120px">{{ $t("batchImportStatus") }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in precheckResults" :key="item.index">
                    <td>
                      <b-checkbox
                        v-model="selectedIndexes"
                        :native-value="item.index"
                        :disabled="!item.can_import && !includeWithWarnings"
                      ></b-checkbox>
                    </td>
                    <td>{{ item.index + 1 }}</td>
                    <td>
                      <div>
                        <a :href="item.url" target="_blank" class="is-small">{{ item.url }}</a>
                      </div>
                      <div v-if="item.description" class="is-size-7 has-text-grey">
                        {{ item.description }}
                      </div>
                      <div class="mt-1">
                        <b-tag
                          v-for="issue in item.issues"
                          :key="issue"
                          type="is-danger"
                          size="is-small"
                          style="margin-right: 4px;"
                        >
                          {{ getIssueLabel(issue) }}
                        </b-tag>
                        <b-tag
                          v-for="warning in item.warnings"
                          :key="warning"
                          type="is-warning"
                          size="is-small"
                          style="margin-right: 4px;"
                        >
                          {{ getWarningLabel(warning) }}
                        </b-tag>
                      </div>
                    </td>
                    <td>
                      <span v-if="item.can_import" class="has-text-success">
                        <b-icon icon="check"></b-icon> {{ $t("batchImportReady") }}
                      </span>
                      <span v-else class="has-text-danger">
                        <b-icon icon="close"></b-icon> {{ $t("batchImportSkipped") }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="step === 'importing'">
            <div class="has-text-centered">
              <b-progress type="is-primary" :value="importProgress" show-value>{{ importProgress }}%</b-progress>
              <p class="mt-4">{{ $t("batchImportImporting") }}</p>
            </div>
          </div>

          <div v-if="step === 'done'">
            <div class="box has-text-centered">
              <b-icon icon="check-circle" type="is-success" size="is-large"></b-icon>
              <p class="title is-4 mt-3">{{ $t("batchImportDone") }}</p>
              <p class="subtitle">
                {{ $t("batchImportCreatedCount", { count: importResult.total_created }) }}
                <span v-if="importResult.total_failed > 0">
                  ，{{ $t("batchImportFailedCount", { count: importResult.total_failed }) }}
                </span>
                <span v-if="importResult.total_skipped > 0">
                  ，{{ $t("batchImportSkippedCount", { count: importResult.total_skipped }) }}
                </span>
              </p>
              <div v-if="importResult.skipped && importResult.skipped.length > 0" class="mt-4">
                <p class="heading">{{ $t("batchImportSkipped") }}:</p>
                <div class="is-size-7 has-text-left" style="max-height: 150px; overflow-y: auto;">
                  <div v-for="item in importResult.skipped" :key="item.index" class="mb-1">
                    <span class="has-text-grey">#{{ item.index + 1 }}</span>
                    <a :href="item.url" target="_blank" class="ml-2">{{ item.url }}</a>
                    <span class="tag is-warning is-small ml-2">{{ getSkipReasonLabel(item.reason) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
        <footer class="modal-card-foot">
          <button class="button" type="button" @click="$parent.close()">
            {{ $t("closeButton") }}
          </button>
          <button
            v-if="step === 'input'"
            @click="startPrecheck"
            class="button is-primary"
            :disabled="!urlText.trim()"
          >
            {{ $t("batchImportPrecheckButton") }}
          </button>
          <button
            v-if="step === 'result'"
            @click="goBack"
            class="button"
          >
            {{ $t("batchImportBackButton") }}
          </button>
          <button
            v-if="step === 'result'"
            @click="startImport"
            class="button is-primary"
            :disabled="selectedIndexes.length === 0"
          >
            {{ $t("batchImportConfirmButton", { count: selectedIndexes.length }) }}
          </button>
          <button
            v-if="step === 'done'"
            @click="resetAndRestart"
            class="button is-primary"
          >
            {{ $t("batchImportImportMore") }}
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script>
import API from '../api';
import FilterSelect from './FilterSelect.vue';
import Loading from '../utils/Loading';
import AutoComplete from '../utils/AutoComplete';
import bus from '../utils/bus';

export default {
  name: 'BatchImportModal',
  props: {
    username: {
      type: String,
      default: null,
    },
  },
  components: {
    FilterSelect,
  },
  data() {
    return {
      step: 'input',
      urlText: '',
      boardIds: [],
      boardOptions: [],
      defaultTags: [],
      defaultPrivate: false,
      tagOptions: [],
      filteredTagOptions: [],
      precheckResults: [],
      summary: { total: 0, can_import: 0, has_issues: 0, has_warnings: 0 },
      selectedIndexes: [],
      selectAllCanImport: false,
      includeWithWarnings: false,
      precheckProgress: 0,
      importProgress: 0,
      importResult: { total_created: 0, total_failed: 0 },
    };
  },
  created() {
    this.fetchBoardList();
    this.fetchTagList();
  },
  methods: {
    fetchTagList() {
      API.Tag.fetchList().then(
        (resp) => {
          this.tagOptions = resp.data;
        },
      );
    },
    getFilteredTags(text) {
      const filtered = [];
      AutoComplete.getFilteredOptions(
        this.tagOptions,
        text,
      ).forEach(
        (option) => {
          filtered.push(option.name);
        },
      );
      this.filteredTagOptions = filtered;
    },
    fetchBoardList() {
      API.Board.fetchFullList(this.username).then(
        (resp) => {
          const options = [];
          resp.data.forEach(
            (board) => {
              options.push({ name: board.name, value: board.id });
            },
          );
          this.boardOptions = options;
        },
      );
    },
    onSelectBoard(boardIds) {
      this.boardIds = boardIds;
    },
    parseUrlText() {
      const lines = this.urlText.split('\n');
      const pins = [];
      lines.forEach((line) => {
        const trimmed = line.trim();
        if (!trimmed) return;
        if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
          pins.push({
            url: trimmed,
            referer: '',
            description: '',
            tags: this.defaultTags,
            private: this.defaultPrivate,
            board_ids: this.boardIds,
          });
        }
      });
      return pins;
    },
    startPrecheck() {
      const pins = this.parseUrlText();
      if (pins.length === 0) {
        return;
      }
      this.step = 'prechecking';
      this.precheckProgress = 30;

      setTimeout(() => {
        this.precheckProgress = 60;
      }, 300);

      API.Pin.batchPrecheck(pins).then(
        (resp) => {
          this.precheckProgress = 100;
          this.precheckResults = resp.data.results;
          this.summary = resp.data.summary;
          setTimeout(() => {
            this.step = 'result';
            this.selectedIndexes = this.precheckResults
              .filter((r) => r.can_import)
              .map((r) => r.index);
            this.selectAllCanImport = true;
          }, 300);
        },
        (error) => {
          console.log('Precheck error:', error);
          this.step = 'input';
        },
      );
    },
    toggleSelectAll() {
      if (this.selectAllCanImport) {
        this.selectedIndexes = this.precheckResults
          .filter((r) => r.can_import || (this.includeWithWarnings && r.warnings.length > 0))
          .map((r) => r.index);
      } else {
        this.selectedIndexes = [];
      }
    },
    applyIncludeWarnings() {
      if (this.selectAllCanImport) {
        this.toggleSelectAll();
      }
    },
    getIssueLabel(issue) {
      const map = {
        missing_url: this.$t('issueMissingUrl'),
        invalid_board: this.$t('issueInvalidBoard'),
        url_404: this.$t('issueUrl404'),
        multiple_boards_not_allowed: this.$t('issueMultipleBoardsNotAllowed'),
        duplicate_fingerprint: this.$t('issueDuplicateFingerprint'),
      };
      return map[issue] || issue;
    },
    getWarningLabel(warning) {
      const map = {
        missing_board: this.$t('warningMissingBoard'),
        duplicate_boards: this.$t('warningDuplicateBoards'),
        duplicate_fingerprint: this.$t('warningDuplicateFingerprint'),
        duplicate_in_batch: this.$t('warningDuplicateInBatch'),
        similar_fingerprint: this.$t('warningSimilarFingerprint'),
        similar_in_batch: this.$t('warningSimilarInBatch'),
        url_unreachable: this.$t('warningUrlUnreachable'),
        url_fetch_failed: this.$t('warningUrlFetchFailed'),
        used_default_board: this.$t('warningUsedDefaultBoard'),
        invalid_board_skipped: this.$t('warningInvalidBoardSkipped'),
        multiple_boards_trimmed: this.$t('warningMultipleBoardsTrimmed'),
        max_boards_exceeded: this.$t('warningMaxBoardsExceeded'),
        no_valid_board_left: this.$t('warningNoValidBoardLeft'),
      };
      if (warning.startsWith('url_error_')) {
        const code = warning.replace('url_error_', '');
        return this.$t('warningUrlError', { code });
      }
      return map[warning] || warning;
    },
    getSkipReasonLabel(reason) {
      const map = {
        url_became_404: this.$t('skipReasonUrlBecame404'),
        duplicate_fingerprint: this.$t('skipReasonDuplicateFingerprint'),
        board_became_invalid: this.$t('skipReasonBoardBecameInvalid'),
      };
      return map[reason] || reason;
    },
    goBack() {
      this.step = 'input';
      this.precheckResults = [];
      this.selectedIndexes = [];
    },
    startImport() {
      const pins = this.parseUrlText();
      const selectedPins = pins.filter((_, idx) => this.selectedIndexes.includes(idx));

      this.step = 'importing';
      this.importProgress = 20;

      setTimeout(() => {
        this.importProgress = 50;
      }, 300);

      API.Pin.batchImport(selectedPins).then(
        (resp) => {
          this.importProgress = 100;
          this.importResult = resp.data;
          setTimeout(() => {
            this.step = 'done';
            bus.bus.$emit(bus.events.refreshPin);
            this.$emit('batchImportDone', resp.data);
          }, 300);
        },
        (error) => {
          console.log('Import error:', error);
          this.importResult = { total_created: 0, total_failed: selectedPins.length };
          this.step = 'done';
        },
      );
    },
    resetAndRestart() {
      this.step = 'input';
      this.urlText = '';
      this.precheckResults = [];
      this.selectedIndexes = [];
      this.importProgress = 0;
      this.precheckProgress = 0;
    },
  },
};
</script>

<style scoped>
.batch-import-modal .modal-card-body {
  max-height: 70vh;
  overflow-y: auto;
}
</style>
