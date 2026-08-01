<script setup lang="ts">
import { computed, inject, ref, type Ref } from 'vue'
import { useApi } from '@directus/extensions-sdk'

const props = withDefaults(
  defineProps<{
    primaryField?: string
    secondaryField?: string
  }>(),
  {
    primaryField: 'content',
    secondaryField: 'contentEn',
  },
)

const emit = defineEmits<{
  setFieldValue: [payload: { field: string; value: unknown }]
}>()

const api = useApi()
const values = inject('values') as Ref<Record<string, unknown>>

const drawerOpen = ref(false)
const activeTarget = ref<'primary' | 'secondary'>('primary')
const busy = ref(false)

const imageFilter = computed(() => ({
  type: { _starts_with: 'image/' },
}))

const targetField = computed(() =>
  activeTarget.value === 'primary' ? props.primaryField : props.secondaryField,
)

function openDrawer(target: 'primary' | 'secondary'): void {
  activeTarget.value = target
  drawerOpen.value = true
}

function toHtmlImages(
  files: Array<{ id: string; title?: string | null; description?: string | null }>,
): string {
  return files
    .map((file) => {
      const alt = String(file.title || file.description || '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
      return `<p><img src="/assets/${file.id}" alt="${alt}"></p>`
    })
    .join('\n')
}

async function onFilesSelected(selection: string[] | null): Promise<void> {
  drawerOpen.value = false
  if (!selection?.length) return

  busy.value = true
  try {
    const response = await api.get('/files', {
      params: {
        filter: { id: { _in: selection } },
        fields: ['id', 'title', 'description', 'type'],
        limit: selection.length,
      },
    })

    const rows = (response?.data?.data ?? []) as Array<{
      id: string
      title?: string | null
      description?: string | null
      type?: string | null
    }>

    const ordered = selection.map((id) => rows.find((row) => row.id === id) ?? { id })
    const images = ordered.filter((file) => {
      const row = rows.find((r) => r.id === file.id)
      return !row?.type || String(row.type).startsWith('image/')
    })

    if (images.length === 0) return

    const field = targetField.value
    const current = String(values.value?.[field] ?? '')
    const snippet = toHtmlImages(images)
    const next = current.trim() ? `${current.trim()}\n${snippet}` : snippet
    emit('setFieldValue', { field, value: next })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="batch-content-images">
    <p class="hint">
      Стандартна кнопка зображення в Content дозволяє додати лише один файл. Використовуйте ці
      кнопки, щоб вставити кілька фото одразу.
    </p>

    <div class="actions">
      <v-button secondary :loading="busy" @click="openDrawer('primary')">
        <v-icon name="photo_library" left />
        Додати фото до Content
      </v-button>
      <v-button secondary :loading="busy" @click="openDrawer('secondary')">
        <v-icon name="photo_library" left />
        Додати фото до Content En
      </v-button>
    </div>

    <drawer-files
      v-model:active="drawerOpen"
      multiple
      :filter="imageFilter"
      @input="onFilesSelected"
    />
  </div>
</template>

<style scoped>
.batch-content-images {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hint {
  margin: 0;
  color: var(--theme--foreground-subdued);
  font-size: 13px;
  line-height: 1.45;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
