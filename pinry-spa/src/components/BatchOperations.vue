<template>
  <div class="batch-operations-modal">
    <div>
      <div class="modal-card" style="width: 560px;">
        <header class="modal-card-head">
          <p class="modal-card-title">{{ modalTitle }}</p>
          <button class="delete" aria-label="close" @click="$parent.close()"></button>
        </header>
        <section class="modal-card-body">
          <div class="selected-info mb-4">
            <span class="tag is-info is-medium">
              {{ $t("selectedPinsCount", { count: selectedPins.length }) }}
            </span>
          </div>

          <div v-if="operation === 'move' || operation === 'copy'" class="field">
            <label class="label">{{ $t("selectTargetBoard") }}</label>
            <div class="control">
              <FilterSelect
                :allOptions="boardOptions"
                v-on:selected="onSelectBoard"
                :single="true"
              ></FilterSelect>
            </div>
            <p v-if="targetBoardError" class="help is-danger">{{ targetBoardError }}</p>
          </div>

          <div v-if="operation === 'privacy'" class="field">
            <label class="label">{{ $t("selectPrivacyStatus") }}</label>
            <div class="control">
              <label class="radio">
                <input type="radio" v-model="privateFlag" :value="false">
                {{ $t("public") }}
              </label>
              <label class="radio">
                <input type="radio" v-model="privateFlag" :value="true">
                {{ $t("private") }}
              </label>
            </div>
          </div>

          <div v-if="operation === 'delete'" class="notification is-warning">
            {{ $t("deleteWarningMessage") }}
          </div>

          <div v-if="operationResult" class="result-section mt-4">
            <div class="box">
              <div class="columns is-mobile is-centered mb-2">
                <div class="column is-narrow">
                  <span class="tag is-success is-medium">
                    {{ $t("successCount", { count: operationResult.success_count }) }}
                  </span>
                </div>
                <div class="column is-narrow">
                  <span v-if="operationResult.failed_count > 0" class="tag is-danger is-medium">
                    {{ $t("failedCount", { count: operationResult.failed_count }) }}
                  </span>
                </div>
              </div>
              <div v-if="operationResult.results.length > 0" class="results-detail" style="max-height: 200px; overflow-y: auto;">
                <table class="table is-striped is-narrow is-hoverable is-fullwidth">
                  <thead>
                    <tr>
                      <th>{{ $t("pinId") }}</th>
                      <th>{{ $t("status") }}</th>
                      <th>{{ $t("message") }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in operationResult.results" :key="item.pin_id">
                      <td>#{{ item.pin_id }}</td>
                      <td>
                        <span :class="item.success ? 'tag is-success is-light' : 'tag is-danger is-light'">
                          {{ item.success ? $t("success") : $t("failed") }}
                        </span>
                      </td>
                      <td class="is-size-7">{{ item.message }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>
        <footer class="modal-card-foot">
          <button class="button" type="button" @click="$parent.close()">{{ $t("closeButton") }}</button>
          <button
            v-if="!operationResult"
            @click="executeOperation"
            :class="['button', confirmButtonClass]"
            :disabled="isExecuting || !canExecute">
            <span class="icon is-small" v-if="isExecuting">
              <i class="mdi mdi-loading mdi-spin"></i>
            </span>
            <span>{{ confirmButtonText }}</span>
          </button>
          <button
            v-else
            @click="finishOperation"
            class="button is-primary">
            {{ $t("finishButton") }}
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script>
import API from './api';
import FilterSelect from './pin_edit/FilterSelect.vue';

export default {
  name: 'BatchOperations',
  components: {
    FilterSelect,
  },
  props: {
    operation: {
      type: String,
      required: true,
      validator: value => ['move', 'copy', 'delete', 'privacy'].includes(value),
    },
    selectedPins: {
      type: Array,
      required: true,
    },
    username: {
      type: String,
      default: null,
    },
    currentBoardId: {
      type: Number,
      default: null,
    },
  },
  data() {
    return {
      boardOptions: [],
      selectedBoardIds: [],
      privateFlag: true,
      isExecuting: false,
      operationResult: null,
      targetBoardError: null,
    };
  },
  computed: {
    modalTitle() {
      const titles = {
        move: 'batchMoveTitle',
        copy: 'batchCopyTitle',
        delete: 'batchDeleteTitle',
        privacy: 'batchPrivacyTitle',
      };
      return this.$t(titles[this.operation]);
    },
    confirmButtonText() {
      const texts = {
        move: 'batchMoveConfirm',
        copy: 'batchCopyConfirm',
        delete: 'batchDeleteConfirm',
        privacy: 'batchPrivacyConfirm',
      };
      return this.$t(texts[this.operation]);
    },
    confirmButtonClass() {
      const classes = {
        move: 'is-primary',
        copy: 'is-link',
        delete: 'is-danger',
        privacy: 'is-warning',
      };
      return classes[this.operation];
    },
    canExecute() {
      if (this.operation === 'move' || this.operation === 'copy') {
        return this.selectedBoardIds.length === 1;
      }
      if (this.operation === 'privacy') {
        return this.privateFlag !== null;
      }
      return this.selectedPins.length > 0;
    },
  },
  created() {
    if (this.operation === 'move' || this.operation === 'copy') {
      this.fetchBoardList();
    }
  },
  methods: {
    fetchBoardList() {
      if (!this.username) return;
      API.Board.fetchFullList(this.username).then(
        (resp) => {
          this.boardOptions = resp.data.map(
            (board) => ({ name: board.name, value: board.id }),
          ).filter(
            (board) => board.value !== this.currentBoardId || this.operation !== 'move',
          );
        },
        () => {
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('fetchBoardListFailed'),
          });
        },
      );
    },
    onSelectBoard(boardIds) {
      this.selectedBoardIds = boardIds;
      this.targetBoardError = null;
    },
    async executeOperation() {
      if (!this.canExecute) return;

      this.isExecuting = true;
      this.targetBoardError = null;
      const pinIds = this.selectedPins.map(p => p.id);

      try {
        let response;
        switch (this.operation) {
          case 'move':
            response = await API.BatchOperation.movePins(
              pinIds,
              this.selectedBoardIds[0],
              this.currentBoardId,
            );
            break;
          case 'copy':
            response = await API.BatchOperation.copyPins(
              pinIds,
              this.selectedBoardIds[0],
            );
            break;
          case 'delete':
            response = await API.BatchOperation.deletePins(pinIds);
            break;
          case 'privacy':
            response = await API.BatchOperation.updatePrivacy(pinIds, this.privateFlag);
            break;
        }
        this.operationResult = response.data;
        this.emitSucceedEvents();
      } catch (error) {
        if (error.response && error.response.data) {
          if (error.response.data.results) {
            this.operationResult = error.response.data;
          } else {
            this.$buefy.toast.open({
              type: 'is-danger',
              message: this.$t('batchOperationFailed'),
            });
          }
        } else {
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('batchOperationFailed'),
          });
        }
      } finally {
        this.isExecuting = false;
      }
    },
    emitSucceedEvents() {
      if (!this.operationResult) return;
      const succeededIds = this.operationResult.results
        .filter(r => r.success)
        .map(r => r.pin_id);

      if (succeededIds.length === 0) return;

      switch (this.operation) {
        case 'delete':
          this.$emit('batch-delete-succeed', succeededIds);
          break;
        case 'move':
          this.$emit('batch-move-succeed', succeededIds);
          break;
        case 'copy':
          this.$emit('batch-copy-succeed', succeededIds);
          break;
        case 'privacy':
          this.$emit('batch-privacy-succeed', succeededIds);
          break;
      }
    },
    finishOperation() {
      this.$parent.close();
    },
  },
};
</script>

<style lang="scss" scoped>
.selected-info {
  padding-bottom: 0.5rem;
}

.result-section {
  border-top: 1px solid #eee;
  padding-top: 1rem;
}

.results-detail {
  margin-top: 1rem;
}

.mb-4 {
  margin-bottom: 1rem;
}

.mt-4 {
  margin-top: 1rem;
}

.mb-2 {
  margin-bottom: 0.5rem;
}

.field {
  margin-bottom: 1rem;
}

.label {
  margin-bottom: 0.5rem;
}
</style>
