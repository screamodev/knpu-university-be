import { factories } from '@strapi/strapi';

export default factories.createCoreRouter('api::partner.partner', {
  config: {
    find: { auth: false },
    findOne: { auth: false },
  },
});
