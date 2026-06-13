<template>
  <div class="boards-for-user">
    <PHeader></PHeader>
    <UserProfileCard :in-board="true" :username="filters.boardUsername"></UserProfileCard>
    <div v-if="isCurrentUser" class="board-tabs">
      <b-tabs v-model="activeTab" expanded>
        <b-tab-item :label="$t('activeBoards')" value="active">
        </b-tab-item>
        <b-tab-item :label="$t('archivedBoards')" value="archived">
        </b-tab-item>
      </b-tabs>
    </div>
    <Boards :filters="filters" :key="activeTab"></Boards>
  </div>
</template>

<script>
import PHeader from '../components/PHeader.vue';
import UserProfileCard from '../components/UserProfileCard.vue';
import Boards from '../components/Boards.vue';
import API from '../components/api';

export default {
  name: 'Boards4User',
  data() {
    return {
      activeTab: 'active',
      currentUser: null,
      filters: { boardUsername: null, showArchived: false },
    };
  },
  components: {
    PHeader,
    UserProfileCard,
    Boards,
  },
  computed: {
    isCurrentUser() {
      if (!this.currentUser) return false;
      return this.currentUser.username === this.filters.boardUsername;
    },
  },
  watch: {
    activeTab(newVal) {
      this.filters.showArchived = newVal === 'archived';
    },
  },
  created() {
    this.initialize();
  },
  beforeRouteUpdate(to, from, next) {
    this.activeTab = 'active';
    this.filters = { boardUsername: to.params.username, showArchived: false };
    next();
  },
  methods: {
    initialize() {
      this.filters = { boardUsername: this.$route.params.username, showArchived: false };
      API.User.fetchUserInfo().then((user) => {
        this.currentUser = user;
      });
    },
  },
};
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped lang="scss">
</style>
