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
            </div>

            <div v-if="runningTask" class="box has-background-info-light" style="clear: both; margin-top: 1rem;">
              <div class="columns is-vcentered">
                <div class="column is-8">
                  <p class="is-size-5 has-text-weight-semibold">
                    {{ statusLabel(runningTask.status) }}
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
                    class="progress is-primary"
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
              <div class="field is-grouped is-grouped-multiline mb-4">
                <p class="control">
                  <span class="is-size-7 has-text-grey mr-2" style="line-height: 2.25;">
                    {{ $t("errorTypeFilterLabel") }}:
                  </span>
                </p>
                <p class="control" v-for="opt in errorTypeOptions" :key="'ft-' + opt.key">
                  <button
                    class="button is-small"
                    :class="{ 'is-info': todoErrorType === opt.value }"
                    @click="todoErrorType = opt.value; onTodoErrorTypeChange();"
                  >
                    <span>{{ $t(opt.labelKey) }}</span>
                    <span
                      v-if="opt.value === '' && todoStats.total > 0"
                      class="tag is-dark is-light ml-1"
                    >{{ todoStats.total }}</span>
                    <span
                      v-else-if="opt.value !== '' && errorTypeCount(opt.value) > 0"
                      class="tag is-dark is-light ml-1"
                    >{{ errorTypeCount(opt.value) }}</span>
                  </button>
                </p>
              </div>
              <div v-if="loadingTodo" class="has-text-centered py-6">
                <i class="fa fa-spinner fa-spin is-size-3"></i>
              </div>
              <div v-else-if="todoList.length === 0" class="notification is-success is-light has-text-centered py-6">
                <i class="fa fa-check-circle is-size-3 mr-2"></i>
                {{ $t("linkCheckEmptyTodo") }}
              </div>
              <div v-else class="checks-list">
                <div
                  v-for="item in todoList"
                  :key="'todo-' + item.id"
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
                              <span class="tag is-danger is-light ml-2">{{ statusLabel(item.status) }}</span>
                              <span v-if="item.error_type" class="tag ml-1" :class="errorTypeTagClass(item.error_type)">
                                {{ errorTypeLabel(item.error_type) }}
                              </span>
                              <span class="tag is-warning is-light ml-1">{{ actionLabel(item.action_status) }}</span>
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
                            <p v-if="item.pin_detail && item.pin_detail.description" class="is-size-6 mt-2">
                              {{ item.pin_detail.description }}
                            </p>
                          </div>
                        </div>
                        <div class="field is-grouped is-grouped-multiline mt-4">
                          <p class="control">
                            <button class="button is-small is-warning" @click="openSource(item)">
                              <i class="fa fa-external-link mr-1"></i>{{ $t("linkCheckSourceLink") }}
                            </button>
                          </p>
                          <p class="control">
                            <button
                              class="button is-small is-info"
                              :class="{ 'is-loading': recheckingId === item.id }"
                              :disabled="recheckingId === item.id"
                              @click="doRecheck(item)"
                            >
                              <i class="fa fa-refresh mr-1"></i>{{ $t("linkCheckActionButtonRecheck") }}
                            </button>
                          </p>
                          <p class="control">
                            <button class="button is-small" @click="doAction(item, 'ignore')">
                              <i class="fa fa-eye-slash mr-1"></i>{{ $t("linkCheckActionButtonIgnore") }}
                            </button>
                          </p>
                          <p class="control">
                            <button class="button is-small is-success" @click="doAction(item, 'fixed')">
                              <i class="fa fa-wrench mr-1"></i>{{ $t("linkCheckActionButtonFixed") }}
                            </button>
                          </p>
                          <p class="control">
                            <button class="button is-small is-primary" @click="doAction(item, 'handled')">
                              <i class="fa fa-check mr-1"></i>{{ $t("linkCheckActionButtonHandled") }}
                            </button>
                          </p>
                          <p class="control">
                            <button class="button is-small is-danger" @click="confirmDelete(item)">
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
                          }"
                        >{{ statusLabel(task.status) }}</span>
                      </td>
                      <td>{{ task.total_pins }}</td>
                      <td>{{ task.checked_count }}</td>
                      <td><span class="has-text-success">{{ task.success_count }}</span></td>
                      <td><span class="has-text-danger">{{ task.failed_count }}</span></td>
                      <td>
                        <div class="field">
                          <progress
                            class="progress is-small is-primary"
                            :value="task.progress_percent"
                            max="100"
                            style="min-width: 80px;"
                          >{{ task.progress_percent }}%</progress>
                        </div>
                        <span class="is-size-7">{{ task.progress_percent }}%</span>
                      </td>
                      <td class="is-size-7">{{ formatDate(task.created_at) }}</td>
                      <td class="is-size-7">{{ formatDate(task.completed_at) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- All Checks Tab -->
            <div v-if="activeTab === 'all'">
              <div class="field is-grouped is-grouped-multiline mb-4">
                <p class="control">
                  <span class="is-size-7 has-text-grey mr-2" style="line-height: 2.25;">
                    {{ $t("errorTypeFilterLabel") }}:
                  </span>
                </p>
                <p class="control" v-for="opt in errorTypeOptions" :key="'fa-' + opt.key">
                  <button
                    class="button is-small"
                    :class="{ 'is-info': allErrorType === opt.value }"
                    @click="allErrorType = opt.value; onAllErrorTypeChange();"
                  >
                    <span>{{ $t(opt.labelKey) }}</span>
                  </button>
                </p>
              </div>
              <div v-if="loadingAll" class="has-text-centered py-6">
                <i class="fa fa-spinner fa-spin is-size-3"></i>
              </div>
              <div v-else-if="allList.length === 0" class="notification is-info is-light has-text-centered py-6">
                {{ $t("linkCheckEmptyHistory") }}
              </div>
              <div v-else class="checks-list">
                <div
                  v-for="item in allList"
                  :key="'all-' + item.id"
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
                                :class="{
                                  'is-warning is-light': item.status === 'pending',
                                  'is-info is-light': item.status === 'running',
                                  'is-success is-light': item.status === 'success',
                                  'is-danger is-light': item.status === 'failed',
                                }"
                              >{{ statusLabel(item.status) }}</span>
                              <span v-if="item.error_type" class="tag ml-1" :class="errorTypeTagClass(item.error_type)">
                                {{ errorTypeLabel(item.error_type) }}
                              </span>
                              <span
                                class="tag ml-1"
                                :class="{
                                  'is-warning is-light': item.action_status === 'unhandled',
                                  'is-dark is-light': item.action_status === 'ignored',
                                  'is-success is-light': item.action_status === 'fixed',
                                  'is-danger is-light': item.action_status === 'deleted',
                                  'is-primary is-light': item.action_status === 'handled',
                                }"
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
                          </div>
                        </div>
                        <div v-if="item.status === 'failed' && item.action_status === 'unhandled'" class="field is-grouped is-grouped-multiline mt-4">
                          <p class="control">
                            <button class="button is-small is-warning" @click="openSource(item)">
                              <i class="fa fa-external-link mr-1"></i>{{ $t("linkCheckSourceLink") }}
                            </button>
                          </p>
                          <p class="control">
                            <button
                              class="button is-small is-info"
                              :class="{ 'is-loading': recheckingId === item.id }"
                              :disabled="recheckingId === item.id"
                              @click="doRecheck(item)"
                            >
                              <i class="fa fa-refresh mr-1"></i>{{ $t("linkCheckActionButtonRecheck") }}
                            </button>
                          </p>
                          <p class="control">
                            <button class="button is-small" @click="doAction(item, 'ignore')">
                              <i class="fa fa-eye-slash mr-1"></i>{{ $t("linkCheckActionButtonIgnore") }}
                            </button>
                          </p>
                          <p class="control">
                            <button class="button is-small is-success" @click="doAction(item, 'fixed')">
                              <i class="fa fa-wrench mr-1"></i>{{ $t("linkCheckActionButtonFixed") }}
                            </button>
                          </p>
                          <p class="control">
                            <button class="button is-small is-danger" @click="confirmDelete(item)">
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

          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
import PHeader from '../components/PHeader.vue';
import api from '../components/api';

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
      loadingTasks: false,
      loadingAll: false,
      todoList: [],
      todoStats: { total: 0, byType: [] },
      taskList: [],
      allList: [],
      pollTimer: null,
      todoErrorType: '',
      allErrorType: '',
      errorTypeOptions: [
        { value: '', key: 'all', labelKey: 'errorTypeAll' },
        { value: 'connection_refused', key: 'connection_refused', labelKey: 'errorTypeConnectionRefused' },
        { value: 'dns_error', key: 'dns_error', labelKey: 'errorTypeDnsError' },
        { value: 'timeout', key: 'timeout', labelKey: 'errorTypeTimeout' },
        { value: 'too_many_redirects', key: 'too_many_redirects', labelKey: 'errorTypeTooManyRedirects' },
        { value: 'ssl_error', key: 'ssl_error', labelKey: 'errorTypeSslError' },
        { value: 'http_4xx', key: 'http_4xx', labelKey: 'errorTypeHttp4xx' },
        { value: 'http_5xx', key: 'http_5xx', labelKey: 'errorTypeHttp5xx' },
        { value: 'unknown', key: 'unknown', labelKey: 'errorTypeUnknown' },
      ],
    };
  },
  components: {
    PHeader,
  },
  beforeMount() {
    this.initializeUser();
  },
  mounted() {
    this.loadInitialData();
  },
  beforeDestroy() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  },
  methods: {
    initializeUser() {
      const self = this;
      api.User.fetchUserInfo().then(
        (user) => {
          if (user !== null) {
            self.user.meta = user;
            self.user.loggedIn = true;
          }
        },
      );
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
    async loadTodoList() {
      this.loadingTodo = true;
      try {
        const params = {
          status: 'failed',
          action_status: 'unhandled',
          latest: true,
          limit: 100,
        };
        if (this.todoErrorType) {
          params.error_type = this.todoErrorType;
        }
        const resp = await api.LinkCheck.fetchList(params);
        this.todoList = resp.data.results || [];
        this.todoStats.total = resp.data.count || 0;
        this.loadTodoStats();
      } catch (e) {
        console.error('Failed to load todo list', e);
      } finally {
        this.loadingTodo = false;
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
    onAllErrorTypeChange() {
      this.loadAllList();
    },
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
    async loadAllList() {
      this.loadingAll = true;
      try {
        const params = { latest: true, limit: 100 };
        if (this.allErrorType) {
          params.error_type = this.allErrorType;
        }
        const resp = await api.LinkCheck.fetchList(params);
        this.allList = resp.data.results || [];
      } catch (e) {
        console.error('Failed to load all list', e);
      } finally {
        this.loadingAll = false;
      }
    },
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
          this.loadTodoList();
          if (this.activeTab === 'tasks') {
            this.loadTaskList();
          }
        }
      } catch (e) {
        console.error(e);
      }
    },
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
          this.allList.unshift(resp.data);
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
        completed: this.$t("linkCheckTaskCompleted"),
      };
      return map[s] || s;
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
    errorTypeCount(t) {
      const stat = this.todoStats.byType.find(s => s.error_type === t);
      return stat ? stat.count : 0;
    },
  },
};
</script>

<style scoped lang="scss">
.link-check-page {
  min-height: 100vh;
  background: #fafafa;

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
}
</style>
