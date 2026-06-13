<template>
  <div class="link-check-page">
    <PHeader></PHeader>
    <section class="section">
      <div class="container">
        <div class="columns">
          <div class="column is-10 is-offset-1">
            <h1 class="title is-3">
              {{ $t("linkCheckTitle") }}
            </h1>

            <div class="field is-grouped is-pulled-right">
              <p class="control">
                <button
                  class="button is-primary"
                  :class="{ 'is-loading': startingTask }"
                  :disabled="runningTask !== null || startingTask"
                  @click="startNewTask"
                >
                  {{ $t("linkCheckStartButton") }}
                </button>
              </p>
              <p v-if="runningTask" class="control">
                <button
                  class="button is-danger is-light"
                  @click="cancelTask"
                >
                  <i class="fa fa-stop mr-1"></i>{{ $t("linkCheckCancelTask") }}
                </button>
              </p>
            </div>

            <div v-if="runningTask" class="box has-background-info-light" style="clear: both; margin-top: 1rem;">
              <div class="columns is-vcentered">
                <div class="column is-8">
                  <p class="is-size-5 has-text-weight-semibold">
                    {{ taskStatusLabel(runningTask.status) }}
                    <span v-if="runningTask.status === 'running'" class="tag is-info is-light ml-2">
                      {{ runningTask.progress_percent }}%
                    </span>
                  </p>
                  <div class="tags mt-2">
                    <span class="tag">{{ $t("linkCheckTotalPins") }}{{ runningTask.total_pins }}</span>
                    <span class="tag">{{ $t("linkCheckCheckedCount") }}{{ runningTask.checked_count }}</span>
                    <span class="tag is-success">{{ $t("linkCheckSuccessCount") }}{{ runningTask.success_count }}</span>
                    <span class="tag is-danger">{{ $t("linkCheckFailedCount") }}{{ runningTask.failed_count }}</span>
                  </div>
                </div>
                <div class="column is-4">
                  <progress
                    class="progress"
                    :class="{
                      'is-primary': runningTask.status === 'running',
                      'is-warning': runningTask.status === 'pending',
                    }"
                    :value="runningTask.progress_percent"
                    max="100"
                  >{{ runningTask.progress_percent }}%</progress>
                </div>
              </div>
            </div>

            <div style="clear: both;"></div>

            <div class="tabs is-boxed mt-4">
              <ul>
                <li :class="{ 'is-active': activeTab === 'todo' }">
                  <a @click="setTab('todo')">
                    {{ $t("linkCheckTodoTab") }}
                    <span v-if="todoStats.total > 0" class="tag is-danger is-light ml-1">
                      {{ todoStats.total }}
                    </span>
                  </a>
                </li>
                <li :class="{ 'is-active': activeTab === 'tasks' }">
                  <a @click="setTab('tasks')">
                    {{ $t("linkCheckTaskTab") }}
                  </a>
                </li>
                <li :class="{ 'is-active': activeTab === 'all' }">
                  <a @click="setTab('all')">
                    {{ $t("linkCheckAllTab") }}
                  </a>
                </li>
              </ul>
            </div>

            <!-- Todo Tab -->
            <div v-if="activeTab === 'todo'">
              <LinkCheckFilterBar
                v-model="todoErrorType"
                :options="errorTypeOptions"
                :total-count="todoStats.total"
                :type-stats="todoStats.byType"
                @input="onTodoErrorTypeChange"
              />
              <LinkCheckTable
                :items="todoList"
                :loading="loadingTodo"
                :loading-more="loadingTodoMore"
                :has-more="todoHasMore"
                :rechecking-id="recheckingId"
                prefix="todo-"
                @open-source="openSource"
                @recheck="doRecheck"
                @action="doAction"
                @confirm-delete="confirmDelete"
                @load-more="loadTodoMore"
              />
            </div>

            <!-- Tasks Tab -->
            <div v-if="activeTab === 'tasks'">
              <div v-if="loadingTasks" class="has-text-centered py-6">
                <i class="fa fa-spinner fa-spin is-size-3"></i>
              </div>
              <div v-else-if="taskList.length === 0" class="notification is-info is-light has-text-centered py-6">
                {{ $t("linkCheckNoTasks") }}
              </div>
              <div v-else class="task-list">
                <table class="table is-fullwidth is-striped is-hoverable">
                  <thead>
                    <tr>
                      <th>#ID</th>
                      <th>Status</th>
                      <th>{{ $t("linkCheckTotalPins") }}</th>
                      <th>{{ $t("linkCheckCheckedCount") }}</th>
                      <th>{{ $t("linkCheckSuccessCount") }}</th>
                      <th>{{ $t("linkCheckFailedCount") }}</th>
                      <th>{{ $t("linkCheckProgress") }}</th>
                      <th>Created</th>
                      <th>Completed</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="task in taskList" :key="'task-' + task.id">
                      <td><strong>{{ task.id }}</strong></td>
                      <td>
                        <span
                          class="tag"
                          :class="{
                            'is-warning': task.status === 'pending',
                            'is-info': task.status === 'running',
                            'is-success': task.status === 'completed',
                            'is-danger': task.status === 'failed',
                            'is-dark': task.status === 'cancelled',
                          }"
                        >{{ taskStatusLabel(task.status) }}</span>
                      </td>
                      <td>{{ task.total_pins }}</td>
                      <td>{{ task.checked_count }}</td>
                      <td><span class="has-text-success">{{ task.success_count }}</span></td>
                      <td><span class="has-text-danger">{{ task.failed_count }}</span></td>
                      <td>
                        <progress
                          class="progress is-small is-primary"
                          :value="task.progress_percent"
                          max="100"
                          style="min-width: 80px;"
                        >{{ task.progress_percent }}%</progress>
                        <span class="is-size-7">{{ task.progress_percent }}%</span>
                      </td>
                      <td class="is-size-7">{{ formatDate(task.created_at) }}</td>
                      <td class="is-size-7">{{ formatDate(task.completed_at) }}</td>
                      <td>
                        <button
                          v-if="task.status === 'running' || task.status === 'pending'"
                          class="button is-small is-danger is-light"
                          @click="cancelTaskById(task.id)"
                        >
                          <i class="fa fa-stop"></i>
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- All Checks Tab -->
            <div v-if="activeTab === 'all'">
              <LinkCheckFilterBar
                v-model="allErrorType"
                :options="errorTypeOptions"
                :total-count="allTotal"
                :type-stats="[]"
                @input="onAllErrorTypeChange"
              />
              <LinkCheckTable
                :items="allList"
                :loading="loadingAll"
                :loading-more="loadingAllMore"
                :has-more="allHasMore"
                :rechecking-id="recheckingId"
                prefix="all-"
                :show-all-actions="true"
                :empty-text="$t('linkCheckEmptyHistory')"
                @open-source="openSource"
                @recheck="doRecheck"
                @action="doAction"
                @confirm-delete="confirmDelete"
                @load-more="loadAllMore"
              />
            </div>

          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
import PHeader from '../components/PHeader.vue';
import LinkCheckFilterBar from '../components/link-check/LinkCheckFilterBar.vue';
import LinkCheckTable from '../components/link-check/LinkCheckTable.vue';
import api from '../components/api';

const ERROR_TYPE_OPTIONS = [
  { value: '', key: 'all', labelKey: 'errorTypeAll' },
  { value: 'connection_refused', key: 'connection_refused', labelKey: 'errorTypeConnectionRefused' },
  { value: 'dns_error', key: 'dns_error', labelKey: 'errorTypeDnsError' },
  { value: 'timeout', key: 'timeout', labelKey: 'errorTypeTimeout' },
  { value: 'too_many_redirects', key: 'too_many_redirects', labelKey: 'errorTypeTooManyRedirects' },
  { value: 'ssl_error', key: 'ssl_error', labelKey: 'errorTypeSslError' },
  { value: 'http_4xx', key: 'http_4xx', labelKey: 'errorTypeHttp4xx' },
  { value: 'http_5xx', key: 'http_5xx', labelKey: 'errorTypeHttp5xx' },
  { value: 'unknown', key: 'unknown', labelKey: 'errorTypeUnknown' },
];

export default {
  name: 'LinkCheck',
  data() {
    return {
      user: { loggedIn: false, meta: {} },
      activeTab: 'todo',
      startingTask: false,
      recheckingId: null,
      runningTask: null,
      loadingTodo: false,
      loadingTodoMore: false,
      loadingTasks: false,
      loadingAll: false,
      loadingAllMore: false,
      todoList: [],
      todoStats: { total: 0, byType: [] },
      todoHasMore: true,
      todoOffset: 0,
      taskList: [],
      allList: [],
      allTotal: 0,
      allHasMore: true,
      allOffset: 0,
      pollTimer: null,
      todoErrorType: '',
      allErrorType: '',
      errorTypeOptions: ERROR_TYPE_OPTIONS,
      pageSize: 20,
    };
  },
  components: {
    PHeader,
    LinkCheckFilterBar,
    LinkCheckTable,
  },
  beforeMount() {
    this.initializeUser();
  },
  mounted() {
    this.loadInitialData();
  },
  beforeDestroy() {
    this.stopPolling();
  },
  methods: {
    initializeUser() {
      api.User.fetchUserInfo().then((user) => {
        if (user !== null) {
          this.user.meta = user;
          this.user.loggedIn = true;
        }
      });
    },
    setTab(tab) {
      this.activeTab = tab;
      if (tab === 'todo' && this.todoList.length === 0 && !this.loadingTodo) {
        this.loadTodoList();
      } else if (tab === 'tasks' && this.taskList.length === 0 && !this.loadingTasks) {
        this.loadTaskList();
      } else if (tab === 'all' && this.allList.length === 0 && !this.loadingAll) {
        this.loadAllList();
      }
    },
    loadInitialData() {
      this.loadTodoList();
      this.detectRunningTask();
    },

    // ---- Todo ----
    async loadTodoList() {
      this.loadingTodo = true;
      this.todoOffset = 0;
      this.todoHasMore = true;
      try {
        const params = {
          status: 'failed',
          action_status: 'unhandled',
          latest: true,
          limit: this.pageSize,
          offset: 0,
        };
        if (this.todoErrorType) {
          params.error_type = this.todoErrorType;
        }
        const resp = await api.LinkCheck.fetchList(params);
        this.todoList = resp.data.results || [];
        this.todoStats.total = resp.data.count || 0;
        this.todoOffset = this.todoList.length;
        this.todoHasMore = this.todoList.length < (resp.data.count || 0);
        this.loadTodoStats();
      } catch (e) {
        console.error('Failed to load todo list', e);
      } finally {
        this.loadingTodo = false;
      }
    },
    async loadTodoMore() {
      if (this.loadingTodoMore || !this.todoHasMore) return;
      this.loadingTodoMore = true;
      try {
        const params = {
          status: 'failed',
          action_status: 'unhandled',
          latest: true,
          limit: this.pageSize,
          offset: this.todoOffset,
        };
        if (this.todoErrorType) {
          params.error_type = this.todoErrorType;
        }
        const resp = await api.LinkCheck.fetchList(params);
        const newItems = resp.data.results || [];
        this.todoList = this.todoList.concat(newItems);
        this.todoOffset = this.todoList.length;
        this.todoHasMore = this.todoList.length < (resp.data.count || 0);
      } catch (e) {
        console.error('Failed to load more todo items', e);
      } finally {
        this.loadingTodoMore = false;
      }
    },
    async loadTodoStats() {
      try {
        const resp = await api.LinkCheck.fetchErrorTypeStats({
          latest: true,
          only_unhandled: true,
        });
        this.todoStats.byType = resp.data.results || [];
      } catch (e) {
        console.error('Failed to load todo stats', e);
      }
    },
    onTodoErrorTypeChange() {
      this.loadTodoList();
    },

    // ---- Tasks ----
    async loadTaskList() {
      this.loadingTasks = true;
      try {
        const resp = await api.LinkCheckTask.fetchList({ limit: 50 });
        this.taskList = resp.data.results || [];
      } catch (e) {
        console.error('Failed to load task list', e);
      } finally {
        this.loadingTasks = false;
      }
    },

    // ---- All Checks ----
    async loadAllList() {
      this.loadingAll = true;
      this.allOffset = 0;
      this.allHasMore = true;
      try {
        const params = {
          latest: true,
          limit: this.pageSize,
          offset: 0,
        };
        if (this.allErrorType) {
          params.error_type = this.allErrorType;
        }
        const resp = await api.LinkCheck.fetchList(params);
        this.allList = resp.data.results || [];
        this.allTotal = resp.data.count || 0;
        this.allOffset = this.allList.length;
        this.allHasMore = this.allList.length < (resp.data.count || 0);
      } catch (e) {
        console.error('Failed to load all list', e);
      } finally {
        this.loadingAll = false;
      }
    },
    async loadAllMore() {
      if (this.loadingAllMore || !this.allHasMore) return;
      this.loadingAllMore = true;
      try {
        const params = {
          latest: true,
          limit: this.pageSize,
          offset: this.allOffset,
        };
        if (this.allErrorType) {
          params.error_type = this.allErrorType;
        }
        const resp = await api.LinkCheck.fetchList(params);
        const newItems = resp.data.results || [];
        this.allList = this.allList.concat(newItems);
        this.allOffset = this.allList.length;
        this.allHasMore = this.allList.length < (resp.data.count || 0);
      } catch (e) {
        console.error('Failed to load more items', e);
      } finally {
        this.loadingAllMore = false;
      }
    },
    onAllErrorTypeChange() {
      this.loadAllList();
    },

    // ---- Task Lifecycle ----
    async detectRunningTask() {
      try {
        const resp = await api.LinkCheckTask.fetchList({ status: 'running', limit: 1 });
        const results = resp.data.results || [];
        if (results.length > 0) {
          this.runningTask = results[0];
          this.startPolling();
        }
      } catch (e) {
        console.error(e);
      }
    },
    async startNewTask() {
      this.startingTask = true;
      try {
        const resp = await api.LinkCheckTask.start();
        this.runningTask = resp.data;
        this.startPolling();
        if (this.activeTab === 'tasks') {
          this.loadTaskList();
        }
      } catch (e) {
        console.error('Failed to start task', e);
      } finally {
        this.startingTask = false;
      }
    },
    async cancelTask() {
      if (!this.runningTask) return;
      await this.cancelTaskById(this.runningTask.id);
    },
    async cancelTaskById(taskId) {
      try {
        await api.LinkCheckTask.cancel(taskId);
        if (this.runningTask && this.runningTask.id === taskId) {
          this.runningTask = null;
          this.stopPolling();
        }
        this.loadTodoList();
        if (this.activeTab === 'tasks') {
          this.loadTaskList();
        }
      } catch (e) {
        console.error('Failed to cancel task', e);
      }
    },
    startPolling() {
      if (this.pollTimer) return;
      this.pollTimer = setInterval(() => this.pollRunningTask(), 3000);
    },
    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
    },
    async pollRunningTask() {
      if (!this.runningTask) {
        this.stopPolling();
        return;
      }
      try {
        const resp = await api.LinkCheckTask.get(this.runningTask.id);
        this.runningTask = resp.data;
        if (resp.data.status !== 'running' && resp.data.status !== 'pending') {
          this.stopPolling();
          this.runningTask = null;
          this.loadTodoList();
          if (this.activeTab === 'tasks') {
            this.loadTaskList();
          }
        }
      } catch (e) {
        console.error(e);
      }
    },

    // ---- Actions ----
    async doRecheck(item) {
      this.recheckingId = item.id;
      try {
        const resp = await api.LinkCheck.recheck(item.id);
        if (this.activeTab === 'todo') {
          if (resp.data.status !== 'failed' || resp.data.action_status !== 'unhandled') {
            this.todoList = this.todoList.filter(i => i.id !== item.id);
            this.todoStats.total = Math.max(0, this.todoStats.total - 1);
          } else {
            const idx = this.todoList.findIndex(i => i.id === item.id);
            if (idx !== -1) this.todoList.splice(idx, 1, resp.data);
          }
        }
        if (this.activeTab === 'all') {
          this.loadAllList();
        }
      } catch (e) {
        console.error(e);
      } finally {
        this.recheckingId = null;
      }
    },
    async doAction(item, action) {
      try {
        await api.LinkCheck.performAction(item.id, action);
        if (this.activeTab === 'todo') {
          this.todoList = this.todoList.filter(i => i.id !== item.id);
          this.todoStats.total = Math.max(0, this.todoStats.total - 1);
        }
        if (this.activeTab === 'all') {
          this.loadAllList();
        }
      } catch (e) {
        console.error(e);
      }
    },
    confirmDelete(item) {
      if (confirm(this.$t("linkCheckConfirmDelete"))) {
        this.doAction(item, 'delete');
      }
    },
    openSource(item) {
      if (item.url) {
        window.open(item.url, '_blank');
      }
    },

    // ---- Formatting ----
    formatDate(dt) {
      if (!dt) return '—';
      const d = new Date(dt);
      if (isNaN(d.getTime())) return dt;
      return d.toLocaleString();
    },
    taskStatusLabel(s) {
      const map = {
        pending: this.$t("linkCheckTaskPending"),
        running: this.$t("linkCheckTaskRunning"),
        completed: this.$t("linkCheckTaskCompleted"),
        failed: this.$t("linkCheckTaskFailed"),
        cancelled: this.$t("linkCheckTaskCancelled"),
      };
      return map[s] || s;
    },
  },
};
</script>

<style scoped lang="scss">
.link-check-page {
  min-height: 100vh;
  background: #fafafa;
}
</style>
