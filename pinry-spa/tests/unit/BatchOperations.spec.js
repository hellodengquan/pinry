import Vue from 'vue';
import { shallowMount } from '@vue/test-utils';
import BatchOperations from '@/components/BatchOperations.vue';
import { createI18n, createPinItem } from '../helpers';

jest.mock('@/components/api', () => ({
  BatchOperation: {
    movePins: jest.fn(),
    copyPins: jest.fn(),
    deletePins: jest.fn(),
    updatePrivacy: jest.fn(),
  },
  Board: {
    fetchFullList: jest.fn(() => Promise.resolve({ data: [] })),
  },
}));

jest.mock('@/components/pin_edit/FilterSelect.vue', () => ({
  name: 'FilterSelect',
  render: h => h('div', { class: 'filter-select-stub' }),
}));

function createWrapper(options = {}) {
  const i18n = createI18n(options.locale || 'en');
  return shallowMount(BatchOperations, {
    i18n,
    propsData: {
      operation: options.operation || 'delete',
      selectedPins: options.selectedPins || [createPinItem({ id: 1 })],
      username: options.username || 'testuser',
      currentBoardId: options.currentBoardId || null,
    },
    data() {
      return {
        boardOptions: options.boardOptions || [],
        selectedBoardIds: options.selectedBoardIds || [],
        privateFlag: options.privateFlag !== undefined ? options.privateFlag : true,
        isExecuting: false,
        operationResult: options.operationResult || null,
        targetBoardError: null,
      };
    },
  });
}

describe('BatchOperations - 逐项结果多语言展示', () => {
  describe('getLocalizedMessage - 基本翻译逻辑', () => {
    it('根据 code 查找 i18n 翻译并返回 (英文)', () => {
      const wrapper = createWrapper({ locale: 'en' });
      const item = { pin_id: 1, success: true, code: 'success_move', message: 'Moved successfully' };
      const result = wrapper.vm.getLocalizedMessage(item);
      expect(result).toBe('Moved successfully');
    });

    it('根据 code 查找 i18n 翻译并返回 (中文)', () => {
      const wrapper = createWrapper({ locale: 'zh' });
      const item = { pin_id: 1, success: true, code: 'success_move', message: 'Moved successfully' };
      const result = wrapper.vm.getLocalizedMessage(item);
      expect(result).toBe('移动成功');
    });

    it('根据 code 查找 i18n 翻译并返回 (法文)', () => {
      const wrapper = createWrapper({ locale: 'fr' });
      const item = { pin_id: 1, success: true, code: 'success_copy', message: 'Copied successfully' };
      const result = wrapper.vm.getLocalizedMessage(item);
      expect(result).toBe('Copie réussie');
    });
  });

  describe('getLocalizedMessage - 各种 code 的翻译', () => {
    const codeExpectations = [
      { code: 'success_move', en: 'Moved successfully', zh: '移动成功' },
      { code: 'success_copy', en: 'Copied successfully', zh: '复制成功' },
      { code: 'success_delete', en: 'Deleted successfully', zh: '删除成功' },
      { code: 'success_privacy_public', en: 'Set to public', zh: '已设为公开' },
      { code: 'success_privacy_private', en: 'Set to private', zh: '已设为私有' },
      { code: 'pin_not_found', en: 'Pin does not exist', zh: 'Pin 不存在' },
      { code: 'pin_no_permission_access', en: 'No permission to access this pin', zh: '无权访问此 Pin' },
      { code: 'pin_no_permission_owner', en: 'No permission to modify this pin', zh: '无权操作此 Pin' },
      { code: 'target_board_not_found', en: 'Target board does not exist', zh: '目标画板不存在' },
      { code: 'target_board_no_permission', en: 'No permission to modify target board', zh: '无权修改目标画板' },
      { code: 'source_board_not_found', en: 'Source board does not exist', zh: '源画板不存在' },
      { code: 'source_board_no_permission', en: 'No permission to modify source board', zh: '无权修改源画板' },
      { code: 'operation_failed', en: 'Operation failed', zh: '操作失败' },
      { code: 'pin_already_in_board', en: 'Pin already exists in the target board', zh: 'Pin 已存在于目标画板' },
    ];

    codeExpectations.forEach(({ code, en, zh }) => {
      it(`code="${code}" 在英文环境下返回 "${en}"`, () => {
        const wrapper = createWrapper({ locale: 'en' });
        const result = wrapper.vm.getLocalizedMessage({ pin_id: 1, success: false, code, message: en });
        expect(result).toBe(en);
      });

      it(`code="${code}" 在中文环境下返回 "${zh}"`, () => {
        const wrapper = createWrapper({ locale: 'zh' });
        const result = wrapper.vm.getLocalizedMessage({ pin_id: 1, success: false, code, message: en });
        expect(result).toBe(zh);
      });
    });
  });

  describe('getLocalizedMessage - 回退行为', () => {
    it('code 存在但 i18n 中无对应词条时，回退到 item.message', () => {
      const wrapper = createWrapper({ locale: 'en' });
      const item = {
        pin_id: 1,
        success: false,
        code: 'some_unknown_future_code',
        message: 'Fallback English message',
      };
      const result = wrapper.vm.getLocalizedMessage(item);
      expect(result).toBe('Fallback English message');
    });

    it('code 为空字符串时，回退到 item.message', () => {
      const wrapper = createWrapper({ locale: 'en' });
      const item = { pin_id: 1, success: false, code: '', message: 'Raw message' };
      const result = wrapper.vm.getLocalizedMessage(item);
      expect(result).toBe('Raw message');
    });

    it('code 不存在 (undefined) 时，回退到 item.message', () => {
      const wrapper = createWrapper({ locale: 'en' });
      const item = { pin_id: 1, success: false, message: 'Raw message only' };
      const result = wrapper.vm.getLocalizedMessage(item);
      expect(result).toBe('Raw message only');
    });

    it('code 和 message 都不存在时，返回空字符串', () => {
      const wrapper = createWrapper({ locale: 'en' });
      const item = { pin_id: 1, success: false };
      const result = wrapper.vm.getLocalizedMessage(item);
      expect(result).toBe('');
    });

    it('i18n 词条缺失时，即使切换到非英文语言，也回退到英文 message', () => {
      const wrapper = createWrapper({ locale: 'zh' });
      const item = {
        pin_id: 1,
        success: false,
        code: 'nonexistent_code_xyz',
        message: 'English fallback',
      };
      const result = wrapper.vm.getLocalizedMessage(item);
      expect(result).toBe('English fallback');
    });
  });

  describe('getLocalizedMessage - 成功项翻译', () => {
    it('成功删除 (success_delete) 在中文环境显示中文', () => {
      const wrapper = createWrapper({ locale: 'zh' });
      const item = { pin_id: 1, success: true, code: 'success_delete', message: 'Deleted successfully' };
      expect(wrapper.vm.getLocalizedMessage(item)).toBe('删除成功');
    });

    it('隐私设为公开 (success_privacy_public) 在中文环境显示中文', () => {
      const wrapper = createWrapper({ locale: 'zh' });
      const item = { pin_id: 1, success: true, code: 'success_privacy_public', message: 'Privacy set to public' };
      expect(wrapper.vm.getLocalizedMessage(item)).toBe('已设为公开');
    });

    it('隐私设为私有 (success_privacy_private) 在法文环境显示法文', () => {
      const wrapper = createWrapper({ locale: 'fr' });
      const item = { pin_id: 1, success: true, code: 'success_privacy_private', message: 'Privacy set to private' };
      expect(wrapper.vm.getLocalizedMessage(item)).toBe('Défini en privé');
    });
  });
});

describe('BatchOperations - canExecute 计算属性', () => {
  it('delete 操作只要有选中 Pin 就可以执行', () => {
    const wrapper = createWrapper({
      operation: 'delete',
      selectedPins: [createPinItem({ id: 1 })],
    });
    expect(wrapper.vm.canExecute).toBe(true);
  });

  it('delete 操作没有选中 Pin 时不可以执行', () => {
    const wrapper = createWrapper({
      operation: 'delete',
      selectedPins: [],
    });
    expect(wrapper.vm.canExecute).toBe(false);
  });

  it('move 操作需要选中一个目标 Board', () => {
    const wrapper = createWrapper({
      operation: 'move',
      selectedBoardIds: [],
    });
    expect(wrapper.vm.canExecute).toBe(false);

    wrapper.setData({ selectedBoardIds: [5] });
    expect(wrapper.vm.canExecute).toBe(true);
  });

  it('copy 操作需要选中一个目标 Board', () => {
    const wrapper = createWrapper({
      operation: 'copy',
      selectedBoardIds: [],
    });
    expect(wrapper.vm.canExecute).toBe(false);

    wrapper.setData({ selectedBoardIds: [10] });
    expect(wrapper.vm.canExecute).toBe(true);
  });

  it('privacy 操作只要 privateFlag 不为 null 就可以执行', () => {
    const wrapper = createWrapper({
      operation: 'privacy',
      privateFlag: true,
    });
    expect(wrapper.vm.canExecute).toBe(true);

    wrapper.setData({ privateFlag: false });
    expect(wrapper.vm.canExecute).toBe(true);
  });
});

describe('BatchOperations - modalTitle / confirmButtonText 多语言', () => {
  it('modalTitle 随语言切换而变化', () => {
    const wrapperEn = createWrapper({ operation: 'delete', locale: 'en' });
    expect(wrapperEn.vm.modalTitle).toBe('Batch Delete Pins');

    const wrapperZh = createWrapper({ operation: 'delete', locale: 'zh' });
    expect(wrapperZh.vm.modalTitle).toBe('批量删除 Pin');
  });

  it('confirmButtonText 随语言切换而变化', () => {
    const wrapperEn = createWrapper({ operation: 'move', locale: 'en' });
    expect(wrapperEn.vm.confirmButtonText).toBe('Confirm Move');

    const wrapperZh = createWrapper({ operation: 'move', locale: 'zh' });
    expect(wrapperZh.vm.confirmButtonText).toBe('确认移动');
  });

  it('confirmButtonClass 随操作类型变化', () => {
    expect(createWrapper({ operation: 'move' }).vm.confirmButtonClass).toBe('is-primary');
    expect(createWrapper({ operation: 'copy' }).vm.confirmButtonClass).toBe('is-link');
    expect(createWrapper({ operation: 'delete' }).vm.confirmButtonClass).toBe('is-danger');
    expect(createWrapper({ operation: 'privacy' }).vm.confirmButtonClass).toBe('is-warning');
  });
});

describe('BatchOperations - emitSucceedEvents', () => {
  it('delete 操作成功时发出 batch-delete-succeed 事件', () => {
    const wrapper = createWrapper({ operation: 'delete' });
    wrapper.setData({
      operationResult: {
        results: [
          { pin_id: 1, success: true, code: 'success_delete' },
          { pin_id: 2, success: false, code: 'pin_not_found' },
        ],
      },
    });
    wrapper.vm.emitSucceedEvents();
    expect(wrapper.emitted('batch-delete-succeed')).toBeTruthy();
    expect(wrapper.emitted('batch-delete-succeed')[0][0]).toEqual([1]);
  });

  it('move 操作成功时发出 batch-move-succeed 事件', () => {
    const wrapper = createWrapper({ operation: 'move' });
    wrapper.setData({
      operationResult: {
        results: [
          { pin_id: 3, success: true, code: 'success_move' },
        ],
      },
    });
    wrapper.vm.emitSucceedEvents();
    expect(wrapper.emitted('batch-move-succeed')).toBeTruthy();
    expect(wrapper.emitted('batch-move-succeed')[0][0]).toEqual([3]);
  });

  it('copy 操作成功时发出 batch-copy-succeed 事件', () => {
    const wrapper = createWrapper({ operation: 'copy' });
    wrapper.setData({
      operationResult: {
        results: [
          { pin_id: 5, success: true, code: 'success_copy' },
        ],
      },
    });
    wrapper.vm.emitSucceedEvents();
    expect(wrapper.emitted('batch-copy-succeed')).toBeTruthy();
  });

  it('privacy 操作成功时发出 batch-privacy-succeed 事件', () => {
    const wrapper = createWrapper({ operation: 'privacy' });
    wrapper.setData({
      operationResult: {
        results: [
          { pin_id: 7, success: true, code: 'success_privacy_private' },
        ],
      },
    });
    wrapper.vm.emitSucceedEvents();
    expect(wrapper.emitted('batch-privacy-succeed')).toBeTruthy();
  });

  it('全部失败时不发出事件', () => {
    const wrapper = createWrapper({ operation: 'delete' });
    wrapper.setData({
      operationResult: {
        results: [
          { pin_id: 1, success: false, code: 'pin_not_found' },
          { pin_id: 2, success: false, code: 'pin_no_permission_owner' },
        ],
      },
    });
    wrapper.vm.emitSucceedEvents();
    expect(wrapper.emitted('batch-delete-succeed')).toBeFalsy();
    expect(wrapper.emitted('batch-move-succeed')).toBeFalsy();
    expect(wrapper.emitted('batch-copy-succeed')).toBeFalsy();
    expect(wrapper.emitted('batch-privacy-succeed')).toBeFalsy();
  });

  it('operationResult 为 null 时不发出事件', () => {
    const wrapper = createWrapper({ operation: 'delete' });
    wrapper.vm.emitSucceedEvents();
    expect(wrapper.emitted('batch-delete-succeed')).toBeFalsy();
  });
});
