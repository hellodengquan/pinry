import axios from 'axios';
import storage from './utils/storage';
import localeUtils from './utils/i18n';

const API_PREFIX = '/api/v2/';

function getCurrentLocale() {
  return localStorage.getItem('localeCode') || (navigator.language || 'en').split('-')[0];
}

function lookupErrorKey(code, fallbackKey = null) {
  const locale = getCurrentLocale();
  const messages = localeUtils.messages[locale] || localeUtils.messages.en;
  const specificKey = `ERROR_${code}`;
  if (messages[specificKey]) return messages[specificKey];
  if (fallbackKey && messages[fallbackKey]) return messages[fallbackKey];

  if (code !== null && typeof code === 'number') {
    const prefix = Math.floor(code / 100) * 100;
    const prefixKey = `ERROR_${prefix}`;
    if (messages[prefixKey]) return messages[prefixKey];
  }
  return null;
}

class ApiError {
  constructor(code, message, detail, fieldErrors, rawData, status) {
    this.code = code;
    this.message = message;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
    this.data = rawData;
    this.status = status;
  }
}

function extractFieldErrors(data) {
  const fieldErrors = {};
  const skipKeys = ['code', 'message', 'detail'];
  Object.entries(data).forEach(([key, value]) => {
    if (!skipKeys.includes(key)) {
      if (Array.isArray(value)) {
        fieldErrors[key] = value[0] || '';
      } else if (typeof value === 'string') {
        fieldErrors[key] = value;
      }
    }
  });

  if (Object.keys(fieldErrors).length === 0 && data.detail && typeof data.detail === 'object') {
    Object.entries(data.detail).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        fieldErrors[key] = value[0] || '';
      } else if (typeof value === 'string') {
        fieldErrors[key] = value;
      }
    });
  }

  return fieldErrors;
}

function extractFieldErrorsFromLegacy(data) {
  const fieldErrors = {};
  Object.entries(data).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      fieldErrors[key] = value[0] || '';
    } else if (typeof value === 'string') {
      fieldErrors[key] = value;
    }
  });
  return fieldErrors;
}

function parseErrorData(data) {
  if (!data || typeof data !== 'object') {
    return new ApiError(
      null,
      typeof data === 'string' ? data : '',
      null,
      {},
      data,
      null,
    );
  }

  const hasNewFormat = 'code' in data && 'message' in data && 'detail' in data;

  if (hasNewFormat) {
    const { code, message, detail } = data;
    return new ApiError(code, message || '', detail, extractFieldErrors(data), data, null);
  }

  return new ApiError(null, '', data, extractFieldErrorsFromLegacy(data), data, null);
}

axios.interceptors.response.use(
  response => response,
  (err) => {
    const enriched = Object.assign({}, err);
    if (err.response) {
      const apiError = parseErrorData(err.response.data);
      apiError.status = err.response.status;
      enriched.apiError = apiError;
    } else {
      enriched.apiError = new ApiError(null, err.message || 'Network error', null, {}, null, 0);
    }
    return Promise.reject(enriched);
  },
);

function getFieldErrors(errorData) {
  if (!errorData) return {};
  if (errorData instanceof ApiError) {
    return errorData.fieldErrors;
  }
  if (errorData && typeof errorData === 'object' && ('code' in errorData || 'message' in errorData)) {
    return extractFieldErrors(errorData);
  }
  return extractFieldErrorsFromLegacy(errorData);
}

function getErrorMessage(errorData, fallbackKey = null) {
  if (!errorData) return '';
  if (errorData instanceof ApiError) {
    const translated = lookupErrorKey(errorData.code, fallbackKey);
    if (translated) return translated;
    if (errorData.message) return errorData.message;
    return '';
  }
  if (typeof errorData === 'string') return errorData;
  if (typeof errorData !== 'object') return '';
  const translated = lookupErrorKey(errorData.code, fallbackKey);
  if (translated) return translated;
  if (errorData.message) return errorData.message;
  if (errorData.detail && typeof errorData.detail === 'string') return errorData.detail;
  return '';
}

function getErrorCode(errorData) {
  if (!errorData) return null;
  if (errorData instanceof ApiError) {
    return errorData.code;
  }
  return errorData.code || null;
}

function getErrorDetail(errorData) {
  if (!errorData) return null;
  if (errorData instanceof ApiError) {
    return errorData.detail;
  }
  return errorData.detail || null;
}

function resolveErrorMessage(apiError, fallbackKey = null) {
  const code = apiError && getErrorCode(apiError);
  const translated = lookupErrorKey(code, fallbackKey);
  if (translated) return translated;
  const backendMsg = getErrorMessage(apiError);
  if (backendMsg) return backendMsg;
  const locale = getCurrentLocale();
  const messages = localeUtils.messages[locale] || localeUtils.messages.en;
  return messages.ERROR_50000 || 'Unknown error';
}

const Board = {
  create(name, private_ = false) {
    const url = `${API_PREFIX}boards/`;
    const data = { name, private: private_ };
    return new Promise(
      (resolve, reject) => {
        axios.post(url, data).then(
          (resp) => {
            if (resp.status !== 201) {
              reject(resp);
            }
            resolve(resp.data);
          },
          (error) => {
            reject(error.apiError || error.response);
          },
        );
      },
    );
  },
  get(boardId) {
    const url = `${API_PREFIX}boards/${boardId}/`;
    return axios.get(url);
  },
  fetchFullList(username) {
    const url = `${API_PREFIX}boards-auto-complete/?submitter__username=${username}`;
    return axios.get(url);
  },
  fetchSiteFullList() {
    const url = `${API_PREFIX}boards-auto-complete/`;
    return axios.get(url);
  },
  fetchListWhichContains(text, offset = 0, limit = 50) {
    const prefix = `${API_PREFIX}boards/?search=${text}`;
    const url = `${prefix}&offset=${offset}&limit=${limit}`;
    return axios.get(url);
  },
  saveChanges(boardId, fieldsForm) {
    const url = `${API_PREFIX}boards/${boardId}/`;
    return axios.patch(
      url,
      fieldsForm,
    );
  },
  addToBoard(boardId, pinIds) {
    const url = `${API_PREFIX}boards/${boardId}/`;
    return axios.patch(
      url,
      { pins_to_add: pinIds },
    );
  },
  removeFromBoard(boardId, pinIds) {
    const url = `${API_PREFIX}boards/${boardId}/`;
    return axios.patch(
      url,
      { pins_to_remove: pinIds },
    );
  },
  delete(boardId) {
    const url = `${API_PREFIX}boards/${boardId}/`;
    return axios.delete(url);
  },
};

const Pin = {
  create(jsonData) {
    const url = `${API_PREFIX}pins/`;
    return axios.post(
      url,
      jsonData,
    );
  },
  createFromURL(jsonData) {
    return this.create(jsonData);
  },
  createFromUploaded(jsonData) {
    return this.create(jsonData);
  },
  uploadImage(fileObject) {
    const url = `${API_PREFIX}images/`;
    const data = new FormData();
    data.append('image', fileObject);
    return axios.post(
      url,
      data,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      },
    );
  },
  deleteById(pinId) {
    const url = `${API_PREFIX}pins/${pinId}/`;
    return axios.delete(
      url,
    );
  },
  updateById(pinId, data) {
    const url = `${API_PREFIX}pins/${pinId}/`;
    return axios.patch(
      url,
      data,
    );
  },
};


function fetchPins(offset, tagFilter, userFilter, boardFilter) {
  const url = `${API_PREFIX}pins/`;
  const queryArgs = {
    format: 'json',
    ordering: '-id',
    limit: 30,
    offset,
  };
  if (tagFilter) queryArgs.tags__name = tagFilter;
  if (userFilter) queryArgs.submitter__username = userFilter;
  if (boardFilter) queryArgs.pins__id = boardFilter;
  return axios.get(
    url,
    { params: queryArgs },
  );
}

function fetchPin(pinId) {
  const url = `${API_PREFIX}pins/${pinId}`;
  return new Promise(
    (resolve, reject) => {
      const p = axios.get(
        url,
      );
      p.then(
        (resp) => {
          const response = {
            data: { results: [resp.data], next: null },
          };
          resolve(response);
        },
        (error) => {
          reject(error);
        },
      );
    },
  );
}

function fetchBoardForUser(username, offset = 0, limit = 50) {
  const prefix = `${API_PREFIX}boards/?submitter__username=${username}`;
  const url = `${prefix}&offset=${offset}&limit=${limit}`;
  return axios.get(url);
}

const User = {
  storageKey: 'pinry.user',
  signUp(username, email, password, passwordRepeat) {
    const url = `${API_PREFIX}profile/users/`;
    return new Promise(
      (resolve, reject) => {
        const p = axios.post(
          url,
          {
            username,
            email,
            password,
            password_repeat: passwordRepeat,
          },
        );
        p.then(
          (resp) => {
            if (resp.status !== 201) {
              reject(resp);
            }
            resolve(resp.data);
          },
          (error) => {
            console.log('Failed to sign up due to unexpected error:', error);
            reject(error.apiError || error.response);
          },
        );
      },
    );
  },
  logIn(username, password) {
    const url = `${API_PREFIX}profile/login/`;
    return new Promise(
      (resolve, reject) => {
        const p = axios.post(
          url,
          {
            username,
            password,
          },
        );
        p.then(
          (resp) => {
            if (resp.status !== 200) {
              reject(resp);
            }
            resolve(resp.data);
          },
          (error) => {
            console.log('Failed to log in due to unexpected error:', error);
            reject(error.apiError || error.response);
          },
        );
      },
    );
  },
  logOut() {
    const self = this;
    return new Promise(
      (resolve) => {
        axios.get('/api-auth/logout/').then(
          () => {
            storage.set(self.storageKey, null, 1);
            resolve();
          },
        );
      },
    );
  },
  fetchUserInfoByName(username) {
    const url = `${API_PREFIX}profile/public-users/?username=${username}`;
    return new Promise(
      (resolve) => {
        axios.get(url).then(
          (resp) => {
            const users = resp.data;
            if (users.length === 0) {
              return resolve(null);
            }
            return resolve(users[0]);
          },
        );
      },
    );
  },
  fetchUserInfo(force = false) {
    const self = this;
    if (!force) {
      const userInfo = storage.get(self.storageKey);
      if (userInfo !== null) {
        return new Promise(
          resolve => resolve(userInfo),
        );
      }
    }
    const url = `${API_PREFIX}profile/users/`;
    return new Promise(
      (resolve) => {
        axios.get(url).then(
          (resp) => {
            const users = resp.data;
            if (users.length === 0) {
              return resolve(null);
            }
            const value = users[0];
            storage.set(self.storageKey, value, 60 * 5 * 1000);
            return resolve(users[0]);
          },
        );
      },
    );
  },
};

const Tag = {
  fetchList() {
    const url = `${API_PREFIX}tags-auto-complete/`;
    return axios.get(url);
  },
};

export default {
  Tag,
  Pin,
  Board,
  fetchPin,
  fetchPins,
  fetchBoardForUser,
  User,
  ApiError,
  getFieldErrors,
  getErrorMessage,
  getErrorCode,
  getErrorDetail,
  parseErrorData,
  resolveErrorMessage,
  lookupErrorKey,
};
