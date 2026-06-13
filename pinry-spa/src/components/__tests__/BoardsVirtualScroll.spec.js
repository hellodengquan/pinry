import { describe, it, expect, beforeEach } from 'vitest';
import Vue from 'vue';
import { mount } from '@vue/test-utils';

const CARD_WIDTH = 240;
const CARD_GAP = 15;
const FOOTER_HEIGHT = 72;
const CARD_HEIGHT = CARD_WIDTH + FOOTER_HEIGHT;
const ROW_HEIGHT = CARD_HEIGHT + CARD_GAP;
const VIRTUAL_MODE_THRESHOLD = 100;

function buildBoards(count) {
  const arr = [];
  for (let i = 0; i < count; i += 1) {
    arr.push({
      id: i + 1,
      name: `board-${i + 1}`,
      total_pins: Math.floor(Math.random() * 50),
    });
  }
  return arr;
}

const BoardTestComponent = {
  template: `
    <div>
      <span class="selected-count">{{ selectedIds.length }}</span>
      <span class="mode-indicator">{{ useVirtualScroller ? 'virtual' : 'masonry' }}</span>
      <button class="toggle-select-all" @click="toggleSelectAll">
        {{ isAllSelected ? 'deselect-all' : 'select-all' }}
      </button>

      <div v-if="useVirtualScroller">
        <div
          v-for="row in rows"
          :key="row.rowIndex"
          class="board-row"
          :data-row-index="row.rowIndex"
        >
          <div
            v-for="board in row.boards"
            :key="board.id"
            class="board-card virtual"
            :data-id="board.id"
            :class="{ 'is-selected': isSelected(board.id) }"
            @click="toggleSelect(board.id)"
          >
            <span class="board-name">{{ board.name }}</span>
            <input
              type="checkbox"
              class="select-checkbox"
              :checked="isSelected(board.id)"
              @click.stop="toggleSelect(board.id)"
            />
          </div>
        </div>
      </div>

      <div v-else class="masonry-mode">
        <div
          v-for="board in blocks"
          :key="board.id"
          class="board-card masonry"
          :data-id="board.id"
          :class="{ 'is-selected': isSelected(board.id) }"
          @click="toggleSelect(board.id)"
        >
          <span class="board-name">{{ board.name }}</span>
          <input
            type="checkbox"
            class="select-checkbox"
            :checked="isSelected(board.id)"
            @click.stop="toggleSelect(board.id)"
          />
        </div>
      </div>
    </div>
  `,
  props: {
    blocks: {
      type: Array,
      default: () => [],
    },
    containerWidth: {
      type: Number,
      default: 1200,
    },
  },
  data() {
    return {
      selectedIds: [],
    };
  },
  computed: {
    isAllSelected() {
      if (this.blocks.length === 0) return false;
      return this.blocks.every(b => this.selectedIds.includes(b.id));
    },
    useVirtualScroller() {
      return this.blocks.length >= VIRTUAL_MODE_THRESHOLD;
    },
    columnCount() {
      const cols = Math.floor((this.containerWidth + CARD_GAP) / (CARD_WIDTH + CARD_GAP));
      return Math.max(1, cols || 1);
    },
    rows() {
      if (!this.useVirtualScroller) return [];
      const cols = this.columnCount;
      const result = [];
      for (let i = 0; i < this.blocks.length; i += cols) {
        const chunk = this.blocks.slice(i, i + cols);
        result.push({
          rowIndex: Math.floor(i / cols),
          boards: chunk,
        });
      }
      return result;
    },
  },
  methods: {
    isSelected(id) {
      return this.selectedIds.includes(id);
    },
    toggleSelect(id) {
      const idx = this.selectedIds.indexOf(id);
      if (idx >= 0) {
        this.selectedIds.splice(idx, 1);
      } else {
        this.selectedIds.push(id);
      }
    },
    toggleSelectAll() {
      if (this.isAllSelected) {
        this.selectedIds = [];
      } else {
        this.selectedIds = this.blocks.map(b => b.id);
      }
    },
  },
};

describe('Boards 多选 + 虚拟滚动', () => {
  describe('少量数据（<100）非虚拟滚动模式', () => {
    let wrapper;

    beforeEach(() => {
      wrapper = mount(BoardTestComponent, {
        propsData: {
          blocks: buildBoards(10),
        },
      });
    });

    it('useVirtualScroller 为 false，rows 为空', () => {
      expect(wrapper.vm.useVirtualScroller).toBe(false);
      expect(wrapper.vm.rows).toEqual([]);
    });

    it('点击卡片可切换选中状态', async () => {
      const firstCard = wrapper.findAll('.board-card').at(0);
      firstCard.trigger('click');
      expect(wrapper.vm.selectedIds).toEqual([1]);
      await Vue.nextTick();
      expect(wrapper.find('.selected-count').text()).toBe('1');
      firstCard.trigger('click');
      expect(wrapper.vm.selectedIds).toEqual([]);
    });

    it('全选按钮可切换全选/取消全选', () => {
      const btn = wrapper.find('.toggle-select-all');
      btn.trigger('click');
      expect(wrapper.vm.selectedIds.length).toBe(10);
      expect(wrapper.vm.isAllSelected).toBe(true);
      btn.trigger('click');
      expect(wrapper.vm.selectedIds.length).toBe(0);
      expect(wrapper.vm.isAllSelected).toBe(false);
    });
  });

  describe('大量数据（500+）虚拟滚动模式', () => {
    let wrapper;
    const TOTAL = 512;

    beforeEach(() => {
      wrapper = mount(BoardTestComponent, {
        propsData: {
          blocks: buildBoards(TOTAL),
          containerWidth: 1200,
        },
      });
    });

    it('useVirtualScroller 为 true', () => {
      expect(wrapper.vm.useVirtualScroller).toBe(true);
    });

    it('columnCount 基于容器宽度正确计算', () => {
      expect(wrapper.vm.columnCount).toBe(4);
    });

    it('rows 计算正确：512 个 / 4 列 = 128 行满行', () => {
      expect(wrapper.vm.rows.length).toBe(128);
      expect(wrapper.vm.rows[0].boards.length).toBe(4);
      expect(wrapper.vm.rows[0].rowIndex).toBe(0);
      expect(wrapper.vm.rows[127].boards.length).toBe(4);
      expect(wrapper.vm.rows[127].boards[3].id).toBe(512);
    });

    it('row 中的 board 顺序与 blocks 一致', () => {
      const row0 = wrapper.vm.rows[0];
      expect(row0.boards[0].id).toBe(1);
      expect(row0.boards[3].id).toBe(4);
      const row1 = wrapper.vm.rows[1];
      expect(row1.boards[0].id).toBe(5);
    });
  });

  describe('长滚动后选中状态稳定性', () => {
    let wrapper;
    const TOTAL = 500;

    beforeEach(() => {
      wrapper = mount(BoardTestComponent, {
        propsData: {
          blocks: buildBoards(TOTAL),
          containerWidth: 1000,
        },
      });
    });

    it('选中头部、中部、尾部各 3 个，selectedIds 总数正确', () => {
      wrapper.vm.toggleSelect(1);
      wrapper.vm.toggleSelect(2);
      wrapper.vm.toggleSelect(3);

      wrapper.vm.toggleSelect(250);
      wrapper.vm.toggleSelect(251);
      wrapper.vm.toggleSelect(252);

      wrapper.vm.toggleSelect(498);
      wrapper.vm.toggleSelect(499);
      wrapper.vm.toggleSelect(500);

      expect(wrapper.vm.selectedIds.length).toBe(9);
      expect(wrapper.vm.isSelected(1)).toBe(true);
      expect(wrapper.vm.isSelected(250)).toBe(true);
      expect(wrapper.vm.isSelected(500)).toBe(true);
    });

    it('模拟反复滚动（rows 重计算）后选中状态不变', () => {
      wrapper.vm.toggleSelect(42);
      wrapper.vm.toggleSelect(123);
      wrapper.vm.toggleSelect(456);

      const before = [...wrapper.vm.selectedIds];

      wrapper.setProps({ containerWidth: 800 });
      const colsAt800 = Math.floor((800 + 15) / (240 + 15));
      expect(wrapper.vm.columnCount).toBe(colsAt800);
      expect(wrapper.vm.rows.length).toBe(Math.ceil(TOTAL / colsAt800));

      const afterResize = [...wrapper.vm.selectedIds];
      expect(afterResize).toEqual(before);
      expect(wrapper.vm.isSelected(42)).toBe(true);
      expect(wrapper.vm.isSelected(123)).toBe(true);
      expect(wrapper.vm.isSelected(456)).toBe(true);

      wrapper.setProps({ containerWidth: 1400 });
      const afterResize2 = [...wrapper.vm.selectedIds];
      expect(afterResize2).toEqual(before);
    });

    it('虚拟滚动模式下全选，所有 500 个都选中', () => {
      wrapper.find('.toggle-select-all').trigger('click');
      expect(wrapper.vm.selectedIds.length).toBe(500);
      expect(wrapper.vm.isAllSelected).toBe(true);
    });

    it('全选后再取消，回到空状态', () => {
      wrapper.find('.toggle-select-all').trigger('click');
      expect(wrapper.vm.selectedIds.length).toBe(500);
      wrapper.find('.toggle-select-all').trigger('click');
      expect(wrapper.vm.selectedIds.length).toBe(0);
      expect(wrapper.vm.isAllSelected).toBe(false);
    });

    it('从非虚拟滚动模式切换到虚拟滚动模式，选中状态保留', async () => {
      const smallWrapper = mount(BoardTestComponent, {
        propsData: {
          blocks: buildBoards(50),
        },
      });
      smallWrapper.vm.toggleSelect(10);
      smallWrapper.vm.toggleSelect(25);
      smallWrapper.vm.toggleSelect(42);
      expect(smallWrapper.vm.selectedIds.length).toBe(3);
      expect(smallWrapper.vm.useVirtualScroller).toBe(false);

      const biggerList = buildBoards(150);
      smallWrapper.setProps({ blocks: biggerList });
      await Vue.nextTick();
      expect(smallWrapper.vm.blocks.length).toBe(150);
      expect(smallWrapper.vm.useVirtualScroller).toBe(true);
      expect(smallWrapper.vm.selectedIds).toEqual([10, 25, 42]);
      expect(smallWrapper.vm.isSelected(10)).toBe(true);
      expect(smallWrapper.vm.isSelected(25)).toBe(true);
      expect(smallWrapper.vm.isSelected(42)).toBe(true);
      expect(smallWrapper.vm.isSelected(99)).toBe(false);
    });

    it('DOM 中只渲染可见行也不会丢失 data 层选中态', () => {
      wrapper.vm.toggleSelect(1);
      wrapper.vm.toggleSelect(500);

      const firstRow = wrapper.find('.board-row[data-row-index="0"]');
      expect(firstRow.exists()).toBe(true);

      const selectedSnapshot = [...wrapper.vm.selectedIds];
      wrapper.setProps({ containerWidth: 600 });
      wrapper.setProps({ containerWidth: 1200 });

      expect(wrapper.vm.selectedIds).toEqual(selectedSnapshot);
      expect(wrapper.vm.isSelected(1)).toBe(true);
      expect(wrapper.vm.isSelected(500)).toBe(true);
    });
  });

  describe('边界情况', () => {
    it('恰好 100 个 board 触发虚拟滚动模式', () => {
      const wrapper = mount(BoardTestComponent, {
        propsData: { blocks: buildBoards(100) },
      });
      expect(wrapper.vm.useVirtualScroller).toBe(true);
      expect(wrapper.vm.rows.length).toBe(25);
    });

    it('99 个 board 不触发虚拟滚动', () => {
      const wrapper = mount(BoardTestComponent, {
        propsData: { blocks: buildBoards(99) },
      });
      expect(wrapper.vm.useVirtualScroller).toBe(false);
      expect(wrapper.vm.rows).toEqual([]);
    });

    it('0 个 board 时 isAllSelected 为 false', () => {
      const wrapper = mount(BoardTestComponent, {
        propsData: { blocks: [] },
      });
      expect(wrapper.vm.isAllSelected).toBe(false);
      expect(wrapper.vm.selectedIds).toEqual([]);
    });

    it('容器宽度小于单张卡片宽度时至少保留 1 列', () => {
      const wrapper = mount(BoardTestComponent, {
        propsData: { blocks: buildBoards(200), containerWidth: 200 },
      });
      expect(wrapper.vm.columnCount).toBe(1);
      expect(wrapper.vm.rows.length).toBe(200);
    });
  });
});
