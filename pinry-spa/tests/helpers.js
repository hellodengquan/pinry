import Vue from 'vue';
import VueI18n from 'vue-i18n';
import Buefy from 'buefy';
import localeUtils from '@/components/utils/i18n';

Vue.use(VueI18n);
Vue.use(Buefy);

export function createI18n(locale = 'en') {
  return new VueI18n({
    locale,
    fallbackLocale: 'en',
    messages: localeUtils.messages,
    silentTranslationWarn: true,
  });
}

export function createPinItem(overrides = {}) {
  return {
    id: overrides.id || 1,
    url: 'https://example.com/thumb.jpg',
    owner_id: overrides.owner_id || 1,
    private: overrides.private || false,
    description: overrides.description || 'Test pin',
    tags: overrides.tags || [],
    author: overrides.author || 'testuser',
    avatar: '//gravatar.com/avatar/abc',
    large_image_url: 'https://example.com/large.jpg',
    original_image_url: 'https://example.com/original.jpg',
    referer: overrides.referer || null,
    orgianl_width: 300,
    style: {
      width: '300px',
      height: '200px',
    },
    class: {},
    ...overrides,
  };
}
