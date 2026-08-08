import { defineDisplay } from '@directus/extensions-sdk'
import DisplayComponent from './display.vue'

export default defineDisplay({
  id: 'text-with-tooltip',
  name: 'Text with tooltip',
  icon: 'tooltip',
  description: 'Truncates long text in tables; hover to read the full value',
  component: DisplayComponent,
  types: ['string', 'text'],
})
