<template>
  <div class="editor">
    <div class="editor-buttons">
      <span class="icon-container" @click="deleteBoard">
         <b-icon
           type="is-light"
           icon="delete"
           custom-size="mdi-24px">
         </b-icon>
      </span>
      <span class="icon-container" @click="toggleArchive" v-if="!board.is_archived">
         <b-icon
           type="is-light"
           icon="archive"
           custom-size="mdi-24px">
         </b-icon>
      </span>
      <span class="icon-container" @click="toggleArchive" v-else>
         <b-icon
           type="is-light"
           icon="unarchive"
           custom-size="mdi-24px">
         </b-icon>
      </span>
      <span class="icon-container" @click="editBoard">
       <b-icon
         type="is-light"
         icon="pencil"
         custom-size="mdi-24px">
       </b-icon>
      </span>
    </div>
  </div>
</template>

<script>
import API from '../api';
import modals from '../modals';


export default {
  name: 'BoardEditor',
  props: {
    board: {
      default() {
        return {};
      },
      type: Object,
    },
  },
  methods: {
    onBoardSaved() {
      this.$emit('board-save-succeed');
    },
    editBoard() {
      modals.openBoardEdit(
        this,
        this.board,
        this.onBoardSaved,
      );
    },
    toggleArchive() {
      const self = this;
      if (this.board.is_archived) {
        this.$buefy.dialog.confirm({
          message: this.$t('unarchiveBoardConfirm'),
          onConfirm: () => {
            API.Board.unarchive(self.board.id).then(
              () => {
                self.$buefy.toast.open(self.$t('boardUnarchived'));
                self.$emit('board-save-succeed', self.board.id);
              },
              () => {
                self.$buefy.toast.open(
                  { type: 'is-danger', message: self.$t('boardUnarchiveFailed') },
                );
              },
            );
          },
        });
      } else {
        this.$buefy.dialog.confirm({
          message: this.$t('archiveBoardConfirm'),
          onConfirm: () => {
            API.Board.archive(self.board.id).then(
              () => {
                self.$buefy.toast.open(self.$t('boardArchived'));
                self.$emit('board-save-succeed', self.board.id);
              },
              () => {
                self.$buefy.toast.open(
                  { type: 'is-danger', message: self.$t('boardArchiveFailed') },
                );
              },
            );
          },
        });
      }
    },
    deleteBoard() {
      this.$buefy.dialog.confirm({
        message: this.$t('deleteBoardConfirm'),
        onConfirm: () => {
          API.Board.delete(this.board.id).then(
            () => {
              this.$buefy.toast.open('Board deleted');
              this.$emit('board-delete-succeed', this.board.id);
            },
            () => {
              this.$buefy.toast.open(
                { type: 'is-danger', message: 'Failed to delete Board' },
              );
            },
          );
        },
      });
    },
  },
};
</script>

<style lang="scss" scoped>
@import './editor';
</style>
