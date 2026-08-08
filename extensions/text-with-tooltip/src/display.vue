<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  value?: string | number | null
}>()

/** Decode common entities so pasted `&quot;` shows as quotes in the list too. */
function decodeEntities(input: string): string {
  if (!input.includes('&')) return input

  return input
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/gi, "'")
    .replace(/&laquo;/gi, '«')
    .replace(/&raquo;/gi, '»')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
}

const text = computed(() => {
  if (props.value === null || props.value === undefined || props.value === '') return null
  return decodeEntities(String(props.value))
})
</script>

<template>
  <span
    v-if="text"
    v-tooltip.top="text"
    class="text-with-tooltip"
    :title="text"
  >{{ text }}</span>
  <span v-else class="empty">—</span>
</template>

<style scoped>
.text-with-tooltip {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty {
  color: var(--theme--foreground-subdued);
}
</style>
