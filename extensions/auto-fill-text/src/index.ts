import { defineInterface } from '@directus/extensions-sdk'
import InterfaceComponent from './interface.vue'

export default defineInterface({
  id: 'auto-fill-text',
  name: 'Auto-fill text',
  icon: 'auto_fix_high',
  description:
    'Multiline text that auto-fills from other fields (like slug). Strips HTML and truncates.',
  component: InterfaceComponent,
  types: ['text', 'string'],
  group: 'standard',
  options: [
    {
      field: 'source',
      name: 'Source',
      type: 'string',
      meta: {
        width: 'full',
        interface: 'input',
        options: {
          placeholder: '{{content}}',
        },
        note: 'Template using other field values, e.g. {{content}} or {{title}}.',
      },
    },
    {
      field: 'maxLength',
      name: 'Max length',
      type: 'integer',
      meta: {
        width: 'half',
        interface: 'input',
        note: 'Plain-text character limit after HTML is stripped.',
      },
      schema: { default_value: 280 },
    },
    {
      field: 'autoGenerate',
      name: '$t:auto_generate',
      type: 'json',
      meta: {
        width: 'half',
        interface: 'select-multiple-dropdown',
        options: {
          choices: [
            { text: '$t:on_create', value: 'create' },
            { text: '$t:on_update', value: 'update' },
          ],
        },
      },
      schema: { default_value: ['create'] },
    },
    {
      field: 'placeholder',
      name: '$t:placeholder',
      type: 'string',
      meta: {
        width: 'full',
        interface: 'system-input-translated-string',
      },
    },
  ],
})
