import { defineInterface } from '@directus/extensions-sdk'
import InterfaceComponent from './interface.vue'

export default defineInterface({
  id: 'cover-hero-focal',
  name: 'Cover + hero frame',
  icon: 'crop_landscape',
  description:
    'Cover image with a movable hero-aspect rectangle and live preview of the public site crop',
  component: InterfaceComponent,
  types: ['uuid'],
  localTypes: ['file'],
  group: 'relational',
  relational: true,
  options: [
    {
      field: 'aspectRatio',
      name: 'Hero aspect ratio (width / height)',
      type: 'float',
      meta: {
        width: 'half',
        interface: 'input',
        note: 'Must match the public article hero (FE uses 5/2 = 2.5).',
      },
      schema: { default_value: 2.5 },
    },
  ],
})
