import { vi } from 'vitest';

global.localStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
  length: 0,
  key: vi.fn(),
};

global.document = {
  cookie: '',
};

Object.defineProperty(window, 'localStorage', {
  value: global.localStorage,
  writable: true,
});
