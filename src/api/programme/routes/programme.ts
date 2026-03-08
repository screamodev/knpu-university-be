import { factories } from '@strapi/strapi';

export default factories.createCoreRouter('api::programme.programme', {
  config: {
    find: { auth: false },
    findOne: { auth: false },
  },
});
