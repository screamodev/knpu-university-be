import type { StrapiApp } from '@strapi/strapi/admin';

export default {
  config: {
    // Ukrainian first so it appears as the primary option in the language switcher.
    // English (en) is always included by Strapi as fallback and cannot be removed.
    locales: ['uk', 'en'],
    translations: {
      uk: {
        'app.components.LeftMenu.navbrand.title': 'Панель керування',
        'app.components.LeftMenu.navbrand.workplace': 'ХНПУ ім. Г. С. Сковороди',
        'Auth.form.welcome.title': 'Панель керування KhNPU',
        'Auth.form.welcome.subtitle': 'Увійдіть у свій обліковий запис',
        'app.components.HomePage.welcome': 'Ласкаво просимо!',
        'app.components.HomePage.welcome.again': 'Ласкаво просимо знову!',
      },
    },
  },
  bootstrap(app: StrapiApp) {},
};
