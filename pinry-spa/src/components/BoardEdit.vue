<template>
  <div class="board-modal">
    <div>
      <div class="modal-card" style="width: auto">
        <header class="modal-card-head">
          <p class="modal-card-title">{{ $t(UIMeta.title) }}</p>
        </header>
        <section class="modal-card-body">
          <div v-if="!isEdit">
            <b-field v-bind:label="$t('nameLabel')"
                       :type="createModel.form.name.type"
                       :message="createModel.form.name.error">
                <b-input
                  type="text"
                  v-model="createModel.form.name.value"
                  v-bind:placeholder="$t('boardNamePlaceholder')"
                  maxlength="128"
                  >
                </b-input>
            </b-field>
            <b-field v-bind:label="$t('privacyOptionLabel')"
                       :type="createModel.form.private.type"
                       :message="createModel.form.private.error">
                <b-checkbox v-model="createModel.form.private.value">
                    {{ $t("isPrivateCheckbox") }}
                </b-checkbox>
              </b-field>
          </div>
          <div v-if="isEdit">
            <b-field v-bind:label="$t('nameLabel')"
                       :type="editModel.form.name.type"
                       :message="editModel.form.name.error">
                <b-input
                  type="text"
                  v-model="editModel.form.name.value"
                  v-bind:placeholder="$t('boardNamePlaceholder')"
                  maxlength="128"
                  >
                </b-input>
            </b-field>
            <b-field v-bind:label="$t('privacyOptionLabel')"
                       :type="editModel.form.private.type"
                       :message="editModel.form.private.error">
                <b-checkbox v-model="editModel.form.private.value">
                    {{ $t("isPrivateCheckbox") }}
                </b-checkbox>
              </b-field>
            <b-field :label="$t('collaboratorsLabel')">
              <div class="collaborators-section">
                <div
                  v-for="collab in collaborators"
                  :key="collab.id"
                  class="collaborator-item"
                >
                  <span class="collaborator-username">{{ collab.username }}</span>
                  <b-select
                    :value="collab.permission"
                    size="is-small"
                    @input="(val) => updatePermission(collab, val)"
                    class="collaborator-permission-select"
                  >
                    <option value="view">{{ $t('permissionView') }}</option>
                    <option value="edit">{{ $t('permissionEdit') }}</option>
                    <option value="manage">{{ $t('permissionManage') }}</option>
                  </b-select>
                  <button
                    class="delete is-small"
                    @click="removeCollaborator(collab)"
                  ></button>
                </div>
                <div class="add-collaborator">
                  <b-input
                    v-model="newCollaboratorUsername"
                    :placeholder="$t('collaboratorUsernamePlaceholder')"
                    size="is-small"
                    class="add-collaborator-input"
                  ></b-input>
                  <b-select
                    v-model="newCollaboratorPermission"
                    size="is-small"
                    class="add-collaborator-permission"
                  >
                    <option value="view">{{ $t('permissionView') }}</option>
                    <option value="edit">{{ $t('permissionEdit') }}</option>
                    <option value="manage">{{ $t('permissionManage') }}</option>
                  </b-select>
                  <button
                    class="button is-small is-primary"
                    @click="addCollaborator"
                    :disabled="!newCollaboratorUsername"
                  >
                    {{ $t('addCollaboratorButton') }}
                  </button>
                </div>
              </div>
            </b-field>
          </div>
        </section>
        <footer class="modal-card-foot">
          <button class="button" type="button" @click="$parent.close()">{{ $t("closeButton") }}</button>
          <button
            v-if="!isEdit"
            @click="createBoard"
            class="button is-primary">{{ $t("createBoardButton") }}
          </button>
          <button
            v-if="isEdit"
            @click="saveBoardChanges"
            class="button is-primary">{{ $t("saveChangesButton") }}
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script>
import API from './api';
import ModelForm from './utils/ModelForm';
import bus from './utils/bus';

const fields = ['name', 'private'];

export default {
  name: 'BoardEditModal',
  data() {
    const createModel = ModelForm.fromFields(fields);
    const editModel = ModelForm.fromFields(fields);
    return {
      UIMeta: {
        title: 'BoardCreateTitle',
      },
      createModel,
      editModel,
      collaborators: [],
      newCollaboratorUsername: '',
      newCollaboratorPermission: 'view',
    };
  },
  props: {
    isEdit: {
      type: Boolean,
      default: false,
    },
    board: {
      type: Object,
      default() {
        return {};
      },
    },
  },
  created() {
    if (this.isEdit) {
      this.UIMeta.title = 'BoardEditTitle';
      this.editModel.assignToForm(this.board);
      this.loadCollaborators();
    } else {
      this.createModel.form.private.value = false;
    }
  },
  methods: {
    loadCollaborators() {
      if (!this.board || !this.board.id) return;
      API.Collaborator.list(this.board.id).then(
        (resp) => {
          this.collaborators = resp.data;
        },
      );
    },
    addCollaborator() {
      if (!this.newCollaboratorUsername) return;
      API.User.fetchUserInfoByName(this.newCollaboratorUsername).then(
        (user) => {
          if (!user) {
            this.$buefy.toast.open({
              type: 'is-danger',
              message: this.$t('userNotFound'),
            });
            return;
          }
          API.Collaborator.add(
            this.board.id,
            user.id,
            this.newCollaboratorPermission,
          ).then(
            () => {
              this.newCollaboratorUsername = '';
              this.newCollaboratorPermission = 'view';
              this.loadCollaborators();
              this.$buefy.toast.open(this.$t('collaboratorAdded'));
            },
            (error) => {
              const msg = error.data && error.data.user
                ? error.data.user.join(', ')
                : this.$t('collaboratorAddFailed');
              this.$buefy.toast.open({ type: 'is-danger', message: msg });
            },
          );
        },
      );
    },
    updatePermission(collab, newPermission) {
      API.Collaborator.update(
        this.board.id,
        collab.id,
        newPermission,
      ).then(
        () => {
          collab.permission = newPermission;
          this.$buefy.toast.open(this.$t('permissionUpdated'));
        },
        () => {
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('permissionUpdateFailed'),
          });
        },
      );
    },
    removeCollaborator(collab) {
      API.Collaborator.remove(this.board.id, collab.id).then(
        () => {
          this.collaborators = this.collaborators.filter(
            (c) => c.id !== collab.id,
          );
          this.$buefy.toast.open(this.$t('collaboratorRemoved'));
        },
        () => {
          this.$buefy.toast.open({
            type: 'is-danger',
            message: this.$t('collaboratorRemoveFailed'),
          });
        },
      );
    },
    saveBoardChanges() {
      const self = this;
      const promise = API.Board.saveChanges(
        this.board.id,
        this.editModel.asData(),
      );
      promise.then(
        (resp) => {
          self.$emit('boardSaved', resp);
          self.$parent.close();
        },
        (error) => {
          self.editModel.markFieldsAsDanger(error.response.data);
        },
      );
    },
    createBoard() {
      const self = this;
      const promise = API.Board.create(
        this.createModel.form.name.value,
        this.createModel.form.private.value,
      );
      promise.then(
        (resp) => {
          bus.bus.$emit(bus.events.refreshBoards);
          self.$emit('boardCreated', resp);
          self.$parent.close();
        },
        (resp) => {
          self.createModel.markFieldsAsDanger(resp.data);
        },
      );
    },
  },
};
</script>

<style scoped>
.collaborators-section {
  width: 100%;
}
.collaborator-item {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  gap: 8px;
}
.collaborator-username {
  flex: 1;
  font-size: 0.9rem;
}
.collaborator-permission-select {
  min-width: 100px;
}
.add-collaborator {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.add-collaborator-input {
  flex: 1;
}
.add-collaborator-permission {
  min-width: 100px;
}
</style>
