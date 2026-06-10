<template>
  <div class="batch-tag-panel">
    <div class="container">
      <div class="section">
        <h1 class="title">{{ $t('batchTagTitle') }}</h1>
        <b-notification
          v-if="!user.loggedIn"
          type="is-warning"
          :closable="false">
          {{ $t('logInLink') }}
        </b-notification>
        <template v-else>
          <b-tabs v-model="activeTab" type="is-boxed">
            <b-tab-item :label="$t('batchTagAddTab')">
              <div class="card">
                <div class="card-content">
                  <b-field :label="$t('batchTagSelectionMode')">
                    <b-radio-button
                      v-model="addSelectionMode"
                      :native-value="'tag'"
                      size="is-small"
                      type="is-primary">
                      <b-icon icon="label"></b-icon>
                      <span>{{ $t('batchTagByTag') }}</span>
                    </b-radio-button>
                    <b-radio-button
                      v-model="addSelectionMode"
                      :native-value="'id'"
                      size="is-small"
                      type="is-primary">
                      <b-icon icon="hash"></b-icon>
                      <span>{{ $t('batchTagById') }}</span>
                    </b-radio-button>
                  </b-field>

                  <b-field
                    v-if="addSelectionMode === 'tag'"
                    :label="$t('batchTagSelectPinByTag')">
                    <b-taginput
                      v-model="form.addPinTagNames"
                      :data="filteredTagOptions"
                      autocomplete
                      ellipsis
                      icon="label"
                      :allow-new="false"
                      :placeholder="$t('batchTagSelectPinByTagPlaceholder')"
                      @typing="getFilteredTags"
                    ></b-taginput>
                    <p class="help">{{ $t('batchTagSelectPinByTagHelp') }}</p>
                  </b-field>

                  <b-field
                    v-if="addSelectionMode === 'id'"
                    :label="$t('batchTagPinIdsLabel')">
                    <b-input
                      v-model="form.pinIdsText"
                      :placeholder="$t('batchTagPinIdsPlaceholder')"
                      type="textarea"
                    ></b-input>
                    <p class="help is-info">{{ $t('batchTagAdvancedMode') }}</p>
                  </b-field>

                  <b-field :label="$t('batchTagAddTagsLabel')">
                    <b-taginput
                      v-model="form.tags"
                      :data="filteredTagOptions"
                      autocomplete
                      ellipsis
                      icon="plus"
                      :allow-new="true"
                      :placeholder="$t('batchTagTagsPlaceholder')"
                      @typing="getFilteredTags"
                    ></b-taginput>
                  </b-field>
                </div>
                <footer class="card-footer">
                  <div class="card-footer-item">
                    <button
                      class="button is-info is-light"
                      :class="{ 'is-loading': previewing }"
                      @click="preview('add')"
                    >{{ $t('batchTagPreviewButton') }}</button>
                  </div>
                  <div class="card-footer-item">
                    <button
                      class="button is-primary"
                      :class="{ 'is-loading': executing }"
                      :disabled="!hasPreview"
                      @click="execute('add')"
                    >{{ $t('batchTagExecuteButton') }}</button>
                  </div>
                </footer>
              </div>
            </b-tab-item>

            <b-tab-item :label="$t('batchTagRemoveTab')">
              <div class="card">
                <div class="card-content">
                  <b-field :label="$t('batchTagSelectionMode')">
                    <b-radio-button
                      v-model="removeSelectionMode"
                      :native-value="'tag'"
                      size="is-small"
                      type="is-primary">
                      <b-icon icon="label"></b-icon>
                      <span>{{ $t('batchTagByTag') }}</span>
                    </b-radio-button>
                    <b-radio-button
                      v-model="removeSelectionMode"
                      :native-value="'id'"
                      size="is-small"
                      type="is-primary">
                      <b-icon icon="hash"></b-icon>
                      <span>{{ $t('batchTagById') }}</span>
                    </b-radio-button>
                  </b-field>

                  <b-field
                    v-if="removeSelectionMode === 'tag'"
                    :label="$t('batchTagSelectPinByTag')">
                    <b-taginput
                      v-model="form.removePinTagNames"
                      :data="filteredTagOptions"
                      autocomplete
                      ellipsis
                      icon="label"
                      :allow-new="false"
                      :placeholder="$t('batchTagSelectPinByTagPlaceholder')"
                      @typing="getFilteredTags"
                    ></b-taginput>
                    <p class="help">{{ $t('batchTagSelectPinByTagHelp') }}</p>
                  </b-field>

                  <b-field
                    v-if="removeSelectionMode === 'id'"
                    :label="$t('batchTagPinIdsLabel')">
                    <b-input
                      v-model="form.pinIdsText"
                      :placeholder="$t('batchTagPinIdsPlaceholder')"
                      type="textarea"
                    ></b-input>
                    <p class="help is-info">{{ $t('batchTagAdvancedMode') }}</p>
                  </b-field>

                  <b-field :label="$t('batchTagRemoveTagsLabel')">
                    <b-taginput
                      v-model="form.tags"
                      :data="filteredTagOptions"
                      autocomplete
                      ellipsis
                      icon="minus"
                      :allow-new="true"
                      :placeholder="$t('batchTagTagsPlaceholder')"
                      @typing="getFilteredTags"
                    ></b-taginput>
                  </b-field>
                </div>
                <footer class="card-footer">
                  <div class="card-footer-item">
                    <button
                      class="button is-info is-light"
                      :class="{ 'is-loading': previewing }"
                      @click="preview('remove')"
                    >{{ $t('batchTagPreviewButton') }}</button>
                  </div>
                  <div class="card-footer-item">
                    <button
                      class="button is-primary"
                      :class="{ 'is-loading': executing }"
                      :disabled="!hasPreview"
                      @click="execute('remove')"
                    >{{ $t('batchTagExecuteButton') }}</button>
                  </div>
                </footer>
              </div>
            </b-tab-item>

            <b-tab-item :label="$t('batchTagMergeTab')">
              <div class="card">
                <div class="card-content">
                  <b-field :label="$t('batchTagSourceTagsLabel')">
                    <b-taginput
                      v-model="form.sourceTags"
                      :data="filteredTagOptions"
                      autocomplete
                      ellipsis
                      icon="label"
                      :allow-new="true"
                      :placeholder="$t('batchTagSourceTagsPlaceholder')"
                      @typing="getFilteredTags"
                    ></b-taginput>
                  </b-field>
                  <b-field :label="$t('batchTagTargetTagLabel')">
                    <b-input
                      v-model="form.targetTag"
                      :placeholder="$t('batchTagTargetTagPlaceholder')"
                    ></b-input>
                  </b-field>
                  <b-notification
                    type="is-info is-light"
                    :closable="false"
                  >{{ $t('batchTagOrphanCleanup') }}</b-notification>
                </div>
                <footer class="card-footer">
                  <div class="card-footer-item">
                    <button
                      class="button is-info is-light"
                      :class="{ 'is-loading': previewing }"
                      @click="preview('merge')"
                    >{{ $t('batchTagPreviewButton') }}</button>
                  </div>
                  <div class="card-footer-item">
                    <button
                      class="button is-primary"
                      :class="{ 'is-loading': executing }"
                      :disabled="!hasPreview"
                      @click="execute('merge')"
                    >{{ $t('batchTagExecuteButton') }}</button>
                  </div>
                </footer>
              </div>
            </b-tab-item>
          </b-tabs>

          <div v-if="previewData" class="preview-section">
            <h2 class="subtitle">{{ $t('batchTagPreviewTitle') }}</h2>

            <div class="columns">
              <div class="column is-half">
                <div class="box">
                  <p class="heading">{{ $t('batchTagAffectedCount') }}</p>
                  <p class="title has-text-success">{{ previewData.affected_count }}</p>
                </div>
              </div>
              <div class="column is-half">
                <div class="box">
                  <p class="heading">{{ $t('batchTagSkippedCount') }}</p>
                  <p class="title has-text-warning">{{ previewData.skipped_count }}</p>
                </div>
              </div>
            </div>

            <b-notification
              v-if="previewData.tag_conflicts && Object.keys(previewData.tag_conflicts).length > 0"
              type="is-warning"
              :closable="false"
            >
              <strong>{{ $t('batchTagCaseConflict') }}</strong>
              <ul>
                <li v-for="(conflict, key) in previewData.tag_conflicts" :key="key">
                  "{{ key }}" {{ $t('batchTagNormalizedTo') }} "{{ conflict.normalized_to }}"
                  <span v-if="conflict.existing_tag">
                    ({{ $t('batchTagExistingTag') }}: "{{ conflict.existing_tag }}")
                  </span>
                  — {{ conflict.message }}
                </li>
              </ul>
            </b-notification>

            <b-notification
              v-if="previewData.aliases && Object.keys(previewData.aliases).length > 0"
              type="is-info"
              :closable="false"
            >
              <strong>{{ $t('batchTagAliasDetected') }}</strong>
              <ul>
                <li v-for="(aliasList, key) in previewData.aliases" :key="key">
                  "{{ key }}" → {{ aliasList.join(', ') }}
                </li>
              </ul>
            </b-notification>

            <b-notification
              v-if="previewData.non_existent_tags && previewData.non_existent_tags.length > 0"
              type="is-danger"
              :closable="false"
            >
              <strong>{{ $t('batchTagNonExistentTags') }}</strong>: {{ previewData.non_existent_tags.join(', ') }}
            </b-notification>

            <div v-if="previewData.pins_already_having_tag && Object.keys(previewData.pins_already_having_tag).length > 0" class="content">
              <h3 class="is-size-6">{{ $t('batchTagPinsAlreadyHavingTag') }}</h3>
              <ul>
                <li v-for="(pinIdList, tagName) in previewData.pins_already_having_tag" :key="tagName">
                  <strong>{{ tagName }}</strong>: {{ pinIdList.join(', ') }}
                </li>
              </ul>
            </div>

            <div v-if="previewData.source_pin_counts && Object.keys(previewData.source_pin_counts).length > 0" class="content">
              <h3 class="is-size-6">{{ $t('batchTagSourcePinCounts') }}</h3>
              <ul>
                <li v-for="(count, tagName) in previewData.source_pin_counts" :key="tagName">
                  <strong>{{ tagName }}</strong>: {{ count }}
                </li>
              </ul>
            </div>

            <div v-if="previewData.target_pin_count !== undefined" class="content">
              <h3 class="is-size-6">{{ $t('batchTagTargetPinCount') }}</h3>
              <p>{{ previewData.target_pin_count }}</p>
            </div>

            <div v-if="previewData.skipped_reasons && Object.keys(previewData.skipped_reasons).length > 0" class="content">
              <h3 class="is-size-6">{{ $t('batchTagSkippedReasons') }}</h3>
              <table class="table is-fullwidth is-striped is-narrow">
                <thead>
                  <tr>
                    <th>{{ $t('batchTagPinId') }}</th>
                    <th>{{ $t('batchTagReason') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(reason, pinId) in previewData.skipped_reasons" :key="pinId">
                    <td>{{ pinId }}</td>
                    <td>{{ reason }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="resultData" class="result-section">
            <h2 class="subtitle">{{ $t('batchTagResultTitle') }}</h2>

            <b-notification
              :type="resultNotificationType"
              :closable="false"
            >{{ resultMessage }}</b-notification>

            <div class="columns">
              <div class="column is-half">
                <div class="box">
                  <p class="heading">{{ $t('batchTagAffectedPins') }}</p>
                  <p class="title has-text-success">{{ resultData.affected_count }}</p>
                  <p v-if="resultData.affected_pin_ids && resultData.affected_pin_ids.length > 0" class="is-size-7">
                    IDs: {{ resultData.affected_pin_ids.join(', ') }}
                  </p>
                </div>
              </div>
              <div class="column is-half">
                <div class="box">
                  <p class="heading">{{ $t('batchTagSkippedPins') }}</p>
                  <p class="title has-text-warning">{{ resultData.skipped_count }}</p>
                  <p v-if="resultData.skipped_pin_ids && resultData.skipped_pin_ids.length > 0" class="is-size-7">
                    IDs: {{ resultData.skipped_pin_ids.join(', ') }}
                  </p>
                </div>
              </div>
            </div>

            <div v-if="resultData.skipped_reasons && Object.keys(resultData.skipped_reasons).length > 0" class="content">
              <h3 class="is-size-6">{{ $t('batchTagSkippedReasons') }}</h3>
              <table class="table is-fullwidth is-striped is-narrow">
                <thead>
                  <tr>
                    <th>{{ $t('batchTagPinId') }}</th>
                    <th>{{ $t('batchTagReason') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(reason, pinId) in resultData.skipped_reasons" :key="pinId">
                    <td>{{ pinId }}</td>
                    <td>{{ reason }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="resultData.errors && resultData.errors.length > 0" class="content">
              <h3 class="is-size-6 has-text-danger">{{ $t('batchTagErrors') }}</h3>
              <table class="table is-fullwidth is-striped is-narrow">
                <thead>
                  <tr>
                    <th>{{ $t('batchTagPinId') }}</th>
                    <th>{{ $t('batchTagErrorDetail') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(error, index) in resultData.errors" :key="index">
                    <td>{{ error.pin_id || '—' }}</td>
                    <td>{{ error.error || error }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="!previewData && !resultData" class="has-text-centered has-text-grey section">
            <p>{{ $t('batchTagNoPreview') }}</p>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script>
import API from './api';
import AutoComplete from './utils/AutoComplete';

export default {
  name: 'BatchTagPanel',
  data() {
    return {
      activeTab: 0,
      addSelectionMode: 'tag',
      removeSelectionMode: 'tag',
      user: {
        loggedIn: false,
        meta: {},
      },
      form: {
        pinIdsText: '',
        addPinTagNames: [],
        removePinTagNames: [],
        tags: [],
        sourceTags: [],
        targetTag: '',
      },
      tagOptions: [],
      filteredTagOptions: [],
      previewing: false,
      executing: false,
      previewData: null,
      resultData: null,
    };
  },
  watch: {
    activeTab() {
      this.previewData = null;
      this.resultData = null;
    },
    addSelectionMode() {
      this.previewData = null;
      this.resultData = null;
    },
    removeSelectionMode() {
      this.previewData = null;
      this.resultData = null;
    },
  },
  computed: {
    hasPreview() {
      return this.previewData !== null;
    },
    currentOperation() {
      return ['add', 'remove', 'merge'][this.activeTab];
    },
    resultNotificationType() {
      if (!this.resultData) return 'is-success';
      if (this.resultData.errors && this.resultData.errors.length > 0) return 'is-danger';
      if (this.resultData.skipped_count > 0) return 'is-warning';
      return 'is-success';
    },
    resultMessage() {
      if (!this.resultData) return '';
      if (this.resultData.errors && this.resultData.errors.length > 0) {
        return this.$t('batchTagPartialSuccess');
      }
      if (this.resultData.skipped_count > 0) {
        return this.$t('batchTagPartialSuccess');
      }
      return this.$t('batchTagSuccess');
    },
  },
  methods: {
    parsePinIds() {
      return this.form.pinIdsText
        .split(/[,\s\n]+/)
        .map(s => s.trim())
        .filter(s => s.length > 0)
        .map(Number)
        .filter(n => !Number.isNaN(n));
    },
    validateForm(operation) {
      if (operation === 'merge') {
        if (this.form.sourceTags.length === 0 || !this.form.targetTag.trim()) {
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('batchTagValidationError'),
          });
          return false;
        }
        const normalizedTarget = this.form.targetTag.trim().toLowerCase();
        const hasSame = this.form.sourceTags.some(
          t => t.toLowerCase() === normalizedTarget,
        );
        if (hasSame) {
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('batchTagMergeSameWarning'),
          });
          return false;
        }
      } else if (operation === 'add') {
        if (this.addSelectionMode === 'id') {
          const pinIds = this.parsePinIds();
          if (pinIds.length === 0 || this.form.tags.length === 0) {
            this.$buefy.toast.open({
              type: 'is-danger',
              message: this.$t('batchTagValidationError'),
            });
            return false;
          }
        } else if (this.form.addPinTagNames.length === 0 || this.form.tags.length === 0) {
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('batchTagValidationError'),
          });
          return false;
        }
      } else if (operation === 'remove') {
        if (this.removeSelectionMode === 'id') {
          const pinIds = this.parsePinIds();
          if (pinIds.length === 0 || this.form.tags.length === 0) {
            this.$buefy.toast.open({
              type: 'is-danger',
              message: this.$t('batchTagValidationError'),
            });
            return false;
          }
        } else if (this.form.removePinTagNames.length === 0 || this.form.tags.length === 0) {
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('batchTagValidationError'),
          });
          return false;
        }
      }
      return true;
    },
    buildPayload(operation) {
      if (operation === 'add') {
        const base = { tags: this.form.tags };
        if (this.addSelectionMode === 'id') {
          return { ...base, pin_ids: this.parsePinIds() };
        }
        return { ...base, pin_tag_names: this.form.addPinTagNames };
      }
      if (operation === 'remove') {
        const base = { tags: this.form.tags };
        if (this.removeSelectionMode === 'id') {
          return { ...base, pin_ids: this.parsePinIds() };
        }
        return { ...base, pin_tag_names: this.form.removePinTagNames };
      }
      return {
        source_tags: this.form.sourceTags,
        target_tag: this.form.targetTag.trim(),
      };
    },
    preview(operation) {
      if (!this.validateForm(operation)) return;
      this.previewing = true;
      this.resultData = null;
      const data = this.buildPayload(operation);
      const payload = { operation, ...data };
      API.BatchTag.preview(payload).then(
        (resp) => {
          this.previewData = resp.data;
          this.previewing = false;
        },
        (error) => {
          this.previewing = false;
          const msg = error.response && error.response.data
            ? JSON.stringify(error.response.data)
            : error.message;
          this.$buefy.toast.open({ type: 'is-danger', message: msg });
        },
      );
    },
    execute(operation) {
      if (!this.hasPreview) return;
      this.$buefy.dialog.confirm({
        message: this.$t('batchTagConfirmExecute'),
        onConfirm: () => {
          this.executing = true;
          this.resultData = null;
          const data = this.buildPayload(operation);
          let promise;
          if (operation === 'add') {
            promise = API.BatchTag.add(data);
          } else if (operation === 'remove') {
            promise = API.BatchTag.remove(data);
          } else {
            promise = API.BatchTag.merge(data);
          }
          promise.then(
            (resp) => {
              this.resultData = resp.data;
              this.previewData = null;
              this.executing = false;
            },
            (error) => {
              this.executing = false;
              const msg = error.response && error.response.data
                ? JSON.stringify(error.response.data)
                : error.message;
              this.$buefy.toast.open({ type: 'is-danger', message: msg });
            },
          );
        },
      });
    },
    getFilteredTags(text) {
      const filteredTagOptions = [];
      AutoComplete.getFilteredOptions(
        this.tagOptions,
        text,
      ).forEach(
        (option) => {
          filteredTagOptions.push(option.name);
        },
      );
      this.filteredTagOptions = filteredTagOptions;
    },
    fetchTagList() {
      API.Tag.fetchList().then(
        (resp) => {
          this.tagOptions = resp.data;
        },
      );
    },
    initializeUser(force = false) {
      const self = this;
      API.User.fetchUserInfo(force).then(
        (user) => {
          if (user === null) {
            self.user.loggedIn = false;
            self.user.meta = {};
          } else {
            self.user.meta = user;
            self.user.loggedIn = true;
          }
        },
      );
    },
  },
  beforeMount() {
    this.initializeUser();
    this.fetchTagList();
  },
};
</script>

<style scoped lang="scss">
.batch-tag-panel {
  min-height: 100vh;
  background-color: #F5F5EB;
}

.preview-section,
.result-section {
  margin-top: 1.5rem;
}

.card-footer-item {
  justify-content: flex-start;
}

.table {
  margin-top: 0.5rem;
}
</style>
