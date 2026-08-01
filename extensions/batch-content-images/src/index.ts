import { defineInterface } from '@directus/extensions-sdk'
import InterfaceComponent from './interface.vue'

export default defineInterface({
  id: 'batch-content-images',
  name: 'Пакетне додавання фото в Content',
  icon: 'photo_library',
  description: 'Оберіть кілька зображень і вставте їх у поля Content / Content En',
  component: InterfaceComponent,
  types: ['alias'],
  localTypes: ['presentation'],
  group: 'presentation',
  options: [
    {
      field: 'primaryField',
      name: 'Primary content field',
      type: 'string',
      meta: {
        width: 'half',
        interface: 'input',
      },
      schema: { default_value: 'content' },
    },
    {
      field: 'secondaryField',
      name: 'Secondary content field',
      type: 'string',
      meta: {
        width: 'half',
        interface: 'input',
      },
      schema: { default_value: 'contentEn' },
    },
  ],
})
