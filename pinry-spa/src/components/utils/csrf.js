import axios from 'axios';
import API from '../api';
import bus from './bus';

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return null;
}


function getCSRFToken() {
  return getCookie('csrftoken');
}

function csrfSafeMethod(method) {
  return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}

let _authCleared = false;

function _clearAuthStore() {
  if (_authCleared) {
    return;
  }
  _authCleared = true;
  try {
    localStorage.removeItem(API.User.storageKey);
  } catch (_err) {
    // ignore
  }
  bus.bus.$emit(bus.events.authChanged);
  setTimeout(() => { _authCleared = false; }, 2000);
}

function setUpAxiosCsrfConfig() {
  axios.interceptors.request.use(
    (config) => {
      if (!csrfSafeMethod(config.method.toUpperCase())) {
        // eslint-disable-next-line no-param-reassign
        config.headers['X-CSRFToken'] = getCSRFToken();
      }
      return config;
    },
    (error) => {
      Promise.reject(error);
    },
  );

  axios.interceptors.response.use(
    (response) => response,
    (error) => {
      const status = error && error.response && error.response.status;
      if (status === 401 || status === 403) {
        _clearAuthStore();
      }
      return Promise.reject(error);
    },
  );
}

export default setUpAxiosCsrfConfig;
