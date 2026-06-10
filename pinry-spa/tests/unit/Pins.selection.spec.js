import Vue from 'vue';
import { shallowMount } from '@vue/test-utils';
import Pins from '@/components/Pins.vue';
import { createI18n, createPinItem } from '../helpers';

jest.mock('@/components/utils/scroll', () => ({
  bindScroll2Bottom: jest.fn(),
}));

jest.mock('@/components/utils/bus', () => ({
  bus: {
    $on: jest.fn(),
    $off: jest.fn(),
    $emit: jest.fn(),
  },
  events: {},
}));

jest.mock('@/components/api', () => ({
  User: {
    fetchUserInfo: jest.fn(() => Promise.resolve(null)),
  },
  Board: {
    get: jest.fn(),
    fetchFullList: jest.fn(),
  },
  fetchPins: jest.fn(() => Promise.resolve({ data: { results: [], next: null } })),
  fetchPin: jest.fn(),
  fetchBoardForUser: jest.fn(),
}));

function createWrapper(options = {}) {
  const i18n = createI18n();
  return shallowMount(Pins, {
    i18n,
    propsData: {
      pinFilters: options.pinFilters || {},
    },
    data() {
      return {
        editorMeta: {
          currentEditId: null,
          currentBoard: options.currentBoard || {},
          user: {
            loggedIn: options.loggedIn || false,
            meta: options.userMeta || { username: 'testuser' },
          },
        },
        blocks: options.blocks || [],
        blocksMap: options.blocksMap || {},
        selectMode: options.selectMode || false,
        selectedIdsMap: options.selectedIdsMap || {},
        status: { loading: false, hasNext: false, offset: 0 },
      };
    },
  });
}

describe('Pins - 选择状态切换', () => {
  it('enterSelectMode 开启选择模式', () => {
    const wrapper = createWrapper({ loggedIn: true });
    expect(wrapper.vm.selectMode).toBe(false);
    wrapper.vm.enterSelectMode();
    expect(wrapper.vm.selectMode).toBe(true);
  });

  it('exitSelectMode 关闭选择模式并清空选择', () => {
    const wrapper = createWrapper({
      loggedIn: true,
      selectMode: true,
      selectedIdsMap: { 1: true, 2: true },
    });
    wrapper.vm.exitSelectMode();
    expect(wrapper.vm.selectMode).toBe(false);
    expect(wrapper.vm.selectedIdsMap).toEqual({});
  });

  it('togglePinSelection 切换单个 Pin 的选中状态', () => {
    const wrapper = createWrapper({ loggedIn: true });
    const pin = createPinItem({ id: 10 });
    wrapper.vm.togglePinSelection(pin);
    expect(wrapper.vm.selectedIdsMap[10]).toBe(true);
    wrapper.vm.togglePinSelection(pin);
    expect(wrapper.vm.selectedIdsMap[10]).toBe(false);
  });

  it('isPinSelected 返回正确的选中状态', () => {
    const wrapper = createWrapper({
      loggedIn: true,
      selectedIdsMap: { 5: true },
    });
    expect(wrapper.vm.isPinSelected(5)).toBe(true);
    expect(wrapper.vm.isPinSelected(99)).toBe(false);
  });

  it('toggleSelectAll(true) 全选', () => {
    const blocks = [
      createPinItem({ id: 1 }),
      createPinItem({ id: 2 }),
      createPinItem({ id: 3 }),
    ];
    const wrapper = createWrapper({ loggedIn: true, blocks });
    wrapper.vm.toggleSelectAll(true);
    expect(wrapper.vm.selectAllChecked).toBe(true);
    expect(wrapper.vm.selectedPins.length).toBe(3);
  });

  it('toggleSelectAll(false) 取消全选', () => {
    const blocks = [
      createPinItem({ id: 1 }),
      createPinItem({ id: 2 }),
    ];
    const wrapper = createWrapper({
      loggedIn: true,
      blocks,
      selectedIdsMap: { 1: true, 2: true },
    });
    wrapper.vm.toggleSelectAll(false);
    expect(wrapper.vm.selectedPins.length).toBe(0);
    expect(wrapper.vm.selectedIdsMap).toEqual({});
  });

  it('selectedPins 只返回被选中的 Pin', () => {
    const blocks = [
      createPinItem({ id: 1 }),
      createPinItem({ id: 2 }),
      createPinItem({ id: 3 }),
    ];
    const wrapper = createWrapper({
      loggedIn: true,
      blocks,
      selectedIdsMap: { 1: true, 3: true },
    });
    expect(wrapper.vm.selectedPins.length).toBe(2);
    expect(wrapper.vm.selectedPins.map(p => p.id)).toEqual([1, 3]);
  });

  it('selectedOwnedPins 只返回当前用户拥有的已选中 Pin', () => {
    const blocks = [
      createPinItem({ id: 1, author: 'testuser' }),
      createPinItem({ id: 2, author: 'otheruser' }),
      createPinItem({ id: 3, author: 'testuser' }),
    ];
    const wrapper = createWrapper({
      loggedIn: true,
      blocks,
      selectedIdsMap: { 1: true, 2: true, 3: true },
      userMeta: { username: 'testuser' },
    });
    expect(wrapper.vm.selectedOwnedPins.length).toBe(2);
    expect(wrapper.vm.selectedOwnedPins.map(p => p.id)).toEqual([1, 3]);
  });

  it('selectAllChecked 在所有可选 Pin 被选中时为 true', () => {
    const blocks = [
      createPinItem({ id: 1 }),
      createPinItem({ id: 2 }),
    ];
    const wrapper = createWrapper({
      loggedIn: true,
      blocks,
      selectedIdsMap: { 1: true, 2: true },
    });
    expect(wrapper.vm.selectAllChecked).toBe(true);
  });

  it('selectAllChecked 在部分选中时为 false', () => {
    const blocks = [
      createPinItem({ id: 1 }),
      createPinItem({ id: 2 }),
    ];
    const wrapper = createWrapper({
      loggedIn: true,
      blocks,
      selectedIdsMap: { 1: true },
    });
    expect(wrapper.vm.selectAllChecked).toBe(false);
  });

  it('selectAllChecked 在没有 Pin 时为 false', () => {
    const wrapper = createWrapper({
      loggedIn: true,
      blocks: [],
      selectedIdsMap: {},
    });
    expect(wrapper.vm.selectAllChecked).toBe(false);
  });

  it('isIndeterminate 在部分选中时为 true', () => {
    const blocks = [
      createPinItem({ id: 1 }),
      createPinItem({ id: 2 }),
    ];
    const wrapper = createWrapper({
      loggedIn: true,
      blocks,
      selectedIdsMap: { 1: true },
    });
    expect(wrapper.vm.isIndeterminate).toBe(true);
  });

  it('isIndeterminate 在全选时为 false', () => {
    const blocks = [
      createPinItem({ id: 1 }),
      createPinItem({ id: 2 }),
    ];
    const wrapper = createWrapper({
      loggedIn: true,
      blocks,
      selectedIdsMap: { 1: true, 2: true },
    });
    expect(wrapper.vm.isIndeterminate).toBe(false);
  });

  it('isIndeterminate 在全不选时为 false', () => {
    const blocks = [
      createPinItem({ id: 1 }),
      createPinItem({ id: 2 }),
    ];
    const wrapper = createWrapper({
      loggedIn: true,
      blocks,
      selectedIdsMap: {},
    });
    expect(wrapper.vm.isIndeterminate).toBe(false);
  });

  it('showBatchToolbar 仅在选择模式且登录时为 true', () => {
    const wrapper1 = createWrapper({ loggedIn: true, selectMode: true });
    expect(wrapper1.vm.showBatchToolbar).toBe(true);

    const wrapper2 = createWrapper({ loggedIn: true, selectMode: false });
    expect(wrapper2.vm.showBatchToolbar).toBe(false);

    const wrapper3 = createWrapper({ loggedIn: false, selectMode: true });
    expect(wrapper3.vm.showBatchToolbar).toBe(false);
  });

  it('isCurrentBoardOwner 在用户是 Board 所有者时为 true', () => {
    const wrapper = createWrapper({
      loggedIn: true,
      currentBoard: { submitter: { username: 'testuser' } },
      userMeta: { username: 'testuser' },
    });
    expect(wrapper.vm.isCurrentBoardOwner).toBe(true);
  });

  it('isCurrentBoardOwner 在用户不是 Board 所有者时为 false', () => {
    const wrapper = createWrapper({
      loggedIn: true,
      currentBoard: { submitter: { username: 'otheruser' } },
      userMeta: { username: 'testuser' },
    });
    expect(wrapper.vm.isCurrentBoardOwner).toBe(false);
  });

  it('isCurrentBoardOwner 在 Board 无 submitter 时为 false', () => {
    const wrapper = createWrapper({
      loggedIn: true,
      currentBoard: {},
      userMeta: { username: 'testuser' },
    });
    expect(wrapper.vm.isCurrentBoardOwner).toBe(false);
  });
});
