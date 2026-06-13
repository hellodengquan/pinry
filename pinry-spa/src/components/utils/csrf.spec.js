import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';

vi.mock('axios', () => {
  const interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  };
  return {
    default: { interceptors },
    interceptors,
    __esModule: true,
  };
});

vi.mock('@/components/utils/bus.js', () => {
  const bus = {
    bus: { $emit: vi.fn() },
    events: {
      refreshPin: 'refreshPin',
      refreshBoards: 'refreshBoards',
      authChanged: 'authChanged',
    },
  };
  return { default: bus, __esModule: true };
});

vi.mock('@/components/api.js', () => ({
  default: {
    User: {
      storageKey: 'pinry_user_info_key',
    },
  },
  __esModule: true,
}));

let busModule;
let apiModule;

describe('csrf.js - 401/403 interceptor', () => {
  let responseInterceptor;
  let requestInterceptor;

  beforeEach(() => {
    vi.resetModules();
    localStorage.removeItem.mockClear();
    localStorage.getItem.mockClear();

    document.cookie = 'csrftoken=test-token';

    // import modules after mocks are set
    busModule = require('@/components/utils/bus.js').default;
    apiModule = require('@/components/api.js').default;

    require('@/components/utils/csrf.js').default();

    // Pull out the registered response interceptor
    responseInterceptor = axios.interceptors.response.use.mock.calls[0][0];
    requestInterceptor = axios.interceptors.request.use.mock.calls[0][0];
  });

  it('registers both request and response interceptors', () => {
    expect(axios.interceptors.request.use).toHaveBeenCalledTimes(1);
    expect(axios.interceptors.response.use).toHaveBeenCalledTimes(1);
  });

  it('attaches CSRF token to unsafe methods via request interceptor', () => {
    const config = { method: 'POST', headers: {} };
    const result = requestInterceptor(config);
    expect(result.headers['X-CSRFToken']).toBe('test-token');
  });

  it('does not attach CSRF token to safe methods', () => {
    const config = { method: 'GET', headers: {} };
    const result = requestInterceptor(config);
    expect(result.headers['X-CSRFToken']).toBeUndefined();
  });

  it('passes through successful responses unchanged', () => {
    const resp = { status: 200, data: { ok: true } };
    const result = responseInterceptor(resp);
    expect(result).toBe(resp);
  });

  it('clears user store on 401 and emits authChanged', () => {
    const error = { response: { status: 401 } };
    let caught;
    try {
      responseInterceptor(error);
    } catch (e) {
      caught = e;
    }
    // The interceptor returns Promise.reject so it should throw/return rejected
    expect(localStorage.removeItem).toHaveBeenCalledWith(apiModule.User.storageKey);
    expect(busModule.bus.$emit).toHaveBeenCalledWith(busModule.events.authChanged);
  });

  it('clears user store on 403 and emits authChanged', () => {
    const error = { response: { status: 403 } };
    try {
      responseInterceptor(error);
    } catch (_) {
      // expected rejection
    }
    expect(localStorage.removeItem).toHaveBeenCalledWith(apiModule.User.storageKey);
    expect(busModule.bus.$emit).toHaveBeenCalledWith(busModule.events.authChanged);
  });

  it('does not clear store on non-auth errors (e.g. 500)', () => {
    const error = { response: { status: 500 } };
    try {
      responseInterceptor(error);
    } catch (_) {}
    expect(localStorage.removeItem).not.toHaveBeenCalled();
    expect(busModule.bus.$emit).not.toHaveBeenCalled();
  });

  it('does not clear store on network error with no response', () => {
    const error = { message: 'Network Error' };
    try {
      responseInterceptor(error);
    } catch (_) {}
    expect(localStorage.removeItem).not.toHaveBeenCalled();
    expect(busModule.bus.$emit).not.toHaveBeenCalled();
  });

  it('debounces rapid 401s to avoid store thrashing', () => {
    vi.useFakeTimers();
    const error = { response: { status: 401 } };

    try { responseInterceptor(error); } catch (_) {}
    try { responseInterceptor(error); } catch (_) {}
    try { responseInterceptor(error); } catch (_) {}

    expect(localStorage.removeItem).toHaveBeenCalledTimes(1);
    expect(busModule.bus.$emit).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(2500);

    try { responseInterceptor(error); } catch (_) {}
    expect(localStorage.removeItem).toHaveBeenCalledTimes(2);
    expect(busModule.bus.$emit).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('handles localStorage access errors gracefully', () => {
    localStorage.removeItem.mockImplementationOnce(() => {
      throw new Error('QuotaExceededError');
    });
    const error = { response: { status: 401 } };
    expect(() => {
      try { responseInterceptor(error); } catch (e) {
        // only re-throw if it's not a Promise rejection from the interceptor
        if (e && e.message === 'QuotaExceededError') throw e;
      }
    }).not.toThrow();
  });
});
