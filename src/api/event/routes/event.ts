import { factories } from '@strapi/strapi';

export default factories.createCoreRouter('api::event.event', {
  config: {
    find: { auth: false },
    findOne: { auth: false },
  },
});
