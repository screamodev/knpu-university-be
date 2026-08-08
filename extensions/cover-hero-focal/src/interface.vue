<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, watch, type Ref } from 'vue'
import { useApi } from '@directus/extensions-sdk'
import {
  defaultFocal,
  focalFromFrame,
  frameFromFocal,
  objectPositionCss,
  type FocalPoint,
  type FrameRect,
  type ImageSize,
} from './geometry'
import { installArticleSaveAndStay, triggerSaveAndStay } from './saveAndStay'

interface FileMeta {
  id: string
  width: number | null
  height: number | null
  focal_point_x: number | null
  focal_point_y: number | null
  title?: string | null
  type?: string | null
}

const props = withDefaults(
  defineProps<{
    value?: string | null
    disabled?: boolean
    aspectRatio?: number
  }>(),
  {
    value: null,
    disabled: false,
    aspectRatio: 2.5,
  },
)

const emit = defineEmits<{
  input: [value: string | null]
  setFieldValue: [payload: { field: string; value: unknown }]
}>()

const api = useApi()
const values = inject<Ref<Record<string, unknown>> | null>('values', null)

let uninstallSaveAndStay: (() => void) | undefined

onMounted(() => {
  uninstallSaveAndStay = installArticleSaveAndStay()
})

onUnmounted(() => {
  uninstallSaveAndStay?.()
  uninstallSaveAndStay = undefined
})

const drawerOpen = ref(false)
const loading = ref(false)
const saving = ref(false)
const saveError = ref<string | null>(null)
const saveOk = ref(false)
const fileMeta = ref<FileMeta | null>(null)
const focal = ref<FocalPoint | null>(null)
const stageRef = ref<HTMLElement | null>(null)
const dragging = ref(false)
const dragOrigin = ref<{
  pointerX: number
  pointerY: number
  frameX: number
  frameY: number
} | null>(null)

const imageFilter = computed(() => ({
  type: { _starts_with: 'image/' },
}))

const ratio = computed(() => (props.aspectRatio > 0 ? props.aspectRatio : 2.5))

const imageSize = computed<ImageSize | null>(() => {
  const width = fileMeta.value?.width
  const height = fileMeta.value?.height
  if (!width || !height) return null
  return { width, height }
})

const frame = computed<FrameRect | null>(() => {
  if (!imageSize.value || !focal.value) return null
  return frameFromFocal(imageSize.value, focal.value, ratio.value)
})

const assetSrc = computed(() => (props.value ? `/assets/${props.value}` : null))

const objectPosition = computed(() => {
  if (!imageSize.value || !focal.value) return '50% 35%'
  return objectPositionCss(imageSize.value, focal.value, ratio.value)
})

/** Frame as % of the displayed (object-contain) image box — we size the stage to the image. */
const frameStyle = computed(() => {
  if (!imageSize.value || !frame.value) return null
  const { width, height } = imageSize.value
  return {
    left: `${(frame.value.x / width) * 100}%`,
    top: `${(frame.value.y / height) * 100}%`,
    width: `${(frame.value.width / width) * 100}%`,
    height: `${(frame.value.height / height) * 100}%`,
  }
})

const previewBoxStyle = computed(() => {
  const base: Record<string, string> = {
    aspectRatio: String(ratio.value),
  }

  if (!assetSrc.value || !imageSize.value || !frame.value) {
    return base
  }

  const { width: imageWidth, height: imageHeight } = imageSize.value
  const { width: frameWidth, height: frameHeight } = frame.value

  return {
    ...base,
    backgroundImage: `url(${assetSrc.value})`,
    backgroundRepeat: 'no-repeat',
    backgroundSize: `${(imageWidth / frameWidth) * 100}% ${(imageHeight / frameHeight) * 100}%`,
    backgroundPosition: objectPosition.value,
  }
})

async function loadFile(id: string): Promise<void> {
  loading.value = true
  saveError.value = null
  saveOk.value = false
  try {
    const response = await api.get(`/files/${id}`, {
      params: {
        fields: ['id', 'width', 'height', 'focal_point_x', 'focal_point_y', 'title', 'type'],
      },
    })
    const data = (response?.data?.data ?? null) as FileMeta | null
    fileMeta.value = data
    if (!data?.width || !data?.height) {
      focal.value = null
      return
    }
    const size = { width: data.width, height: data.height }

    const articleFx = values?.value?.cover_focal_x
    const articleFy = values?.value?.cover_focal_y
    if (typeof articleFx === 'number' && typeof articleFy === 'number') {
      focal.value = { x: articleFx, y: articleFy }
    } else if (typeof data.focal_point_x === 'number' && typeof data.focal_point_y === 'number') {
      focal.value = { x: data.focal_point_x, y: data.focal_point_y }
    } else {
      focal.value = defaultFocal(size)
    }
  } catch {
    fileMeta.value = null
    focal.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => props.value,
  (id) => {
    if (!id) {
      fileMeta.value = null
      focal.value = null
      saveError.value = null
      saveOk.value = false
      return
    }
    void loadFile(id)
  },
  { immediate: true },
)

function setValue(id: string | null): void {
  emit('input', id)
}

function clear(): void {
  if (props.disabled) return
  setValue(null)
  emit('setFieldValue', { field: 'cover_focal_x', value: null })
  emit('setFieldValue', { field: 'cover_focal_y', value: null })
}

function openDrawer(): void {
  if (props.disabled) return
  drawerOpen.value = true
}

function onFilesSelected(selection: string[] | null): void {
  drawerOpen.value = false
  const id = selection?.[0]
  if (!id) return
  setValue(id)
  emit('setFieldValue', { field: 'cover_focal_x', value: null })
  emit('setFieldValue', { field: 'cover_focal_y', value: null })
}

/**
 * Writes focal to the file (public site reads it) and to hidden article fields
 * so the item form becomes dirty and Save enables.
 */
async function persistFocal(next: FocalPoint): Promise<void> {
  const id = props.value
  if (!id || props.disabled) return

  const fx = Math.round(next.x)
  const fy = Math.round(next.y)

  saving.value = true
  saveError.value = null
  saveOk.value = false
  try {
    await api.patch(`/files/${id}`, {
      focal_point_x: fx,
      focal_point_y: fy,
    })
    if (fileMeta.value) {
      fileMeta.value = {
        ...fileMeta.value,
        focal_point_x: fx,
        focal_point_y: fy,
      }
    }

    emit('setFieldValue', { field: 'cover_focal_x', value: fx })
    emit('setFieldValue', { field: 'cover_focal_y', value: fy })
    saveOk.value = true
  } catch {
    saveError.value = 'Не вдалося зберегти область обкладинки'
  } finally {
    saving.value = false
  }
}

function onFramePointerDown(event: PointerEvent): void {
  if (props.disabled || !frame.value || !stageRef.value) return
  event.preventDefault()
  dragging.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  dragOrigin.value = {
    pointerX: event.clientX,
    pointerY: event.clientY,
    frameX: frame.value.x,
    frameY: frame.value.y,
  }
}

function onFramePointerMove(event: PointerEvent): void {
  if (!dragging.value || !dragOrigin.value || !imageSize.value || !frame.value || !stageRef.value) {
    return
  }

  const stage = stageRef.value.getBoundingClientRect()
  const scaleX = imageSize.value.width / stage.width
  const scaleY = imageSize.value.height / stage.height
  const dx = (event.clientX - dragOrigin.value.pointerX) * scaleX
  const dy = (event.clientY - dragOrigin.value.pointerY) * scaleY

  const nextFrame: FrameRect = {
    x: dragOrigin.value.frameX + dx,
    y: dragOrigin.value.frameY + dy,
    width: frame.value.width,
    height: frame.value.height,
  }

  // Clamp via frameFromFocal using intended center
  const intended = focalFromFrame(nextFrame)
  focal.value = focalFromFrame(frameFromFocal(imageSize.value, intended, ratio.value))
}

function onFramePointerUp(event: PointerEvent): void {
  if (!dragging.value) return
  dragging.value = false
  dragOrigin.value = null
  try {
    ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  } catch {
    // already released
  }
  if (focal.value) {
    void persistFocal(focal.value)
  }
}
</script>

<template>
  <div class="cover-hero-focal">
    <div v-if="!value" class="empty">
      <v-button :disabled="disabled" @click="openDrawer">
        <v-icon name="image" left />
        Обрати обкладинку
      </v-button>
    </div>

    <template v-else>
      <div class="toolbar">
        <v-button secondary small :disabled="disabled || loading" @click="openDrawer">
          Замінити
        </v-button>
        <v-button secondary small danger :disabled="disabled || loading" @click="clear">
          Видалити
        </v-button>
        <v-button secondary small :disabled="disabled || loading" @click="triggerSaveAndStay">
          Зберегти (лишитись)
        </v-button>
        <span v-if="saving" class="status">Збереження області…</span>
        <span v-else-if="saveError" class="status error">{{ saveError }}</span>
        <span v-else-if="saveOk" class="status ok">Область оновлено — натисніть Save або ⌘/Ctrl+S</span>
      </div>

      <div v-if="loading" class="loading">Завантаження…</div>

      <template v-else-if="assetSrc && imageSize && frameStyle">
        <p class="hint">
          Перетягніть рамку так, щоб важлива частина фото була всередині. Після зміни рамки
          кнопка Save стане активною.
        </p>

        <div class="stage-wrap">
          <div ref="stageRef" class="stage">
            <img :src="assetSrc" alt="" class="stage-image" draggable="false" />
            <div
              class="frame"
              :class="{ dragging }"
              :style="frameStyle"
              @pointerdown="onFramePointerDown"
              @pointermove="onFramePointerMove"
              @pointerup="onFramePointerUp"
              @pointercancel="onFramePointerUp"
            >
              <span class="frame-label">Область на сайті</span>
            </div>
          </div>
        </div>

        <div class="preview-block">
          <div class="preview-label">Як виглядатиме на сайті (картка / герой)</div>
          <div class="preview" :style="previewBoxStyle" role="img" aria-label="Попередній перегляд обкладинки" />
        </div>
      </template>

      <div v-else-if="assetSrc" class="fallback">
        <img :src="assetSrc" alt="" class="fallback-image" />
        <p class="hint">
          Немає розмірів файлу — рамку показати не можна. Відкрийте файл у бібліотеці або
          завантажте зображення знову.
        </p>
      </div>
    </template>

    <drawer-files
      v-model:active="drawerOpen"
      :filter="imageFilter"
      @input="onFilesSelected"
    />
  </div>
</template>

<style scoped>
.cover-hero-focal {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.empty {
  display: flex;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.status {
  font-size: 12px;
  color: var(--theme--foreground-subdued);
}

.status.error {
  color: var(--theme--danger);
}

.status.ok {
  color: var(--theme--success, var(--theme--primary));
}

.hint {
  margin: 0;
  color: var(--theme--foreground-subdued);
  font-size: 13px;
  line-height: 1.45;
}

.loading {
  color: var(--theme--foreground-subdued);
  font-size: 13px;
}

.stage-wrap {
  width: 100%;
  border: 1px solid var(--theme--border-color);
  border-radius: var(--theme--border-radius);
  overflow: hidden;
  background: var(--theme--background-normal);
}

.stage {
  position: relative;
  width: 100%;
  line-height: 0;
  user-select: none;
  touch-action: none;
}

.stage-image {
  display: block;
  width: 100%;
  height: auto;
  pointer-events: none;
}

.frame {
  position: absolute;
  box-sizing: border-box;
  border: 2px solid #fff;
  box-shadow:
    0 0 0 9999px rgba(0, 0, 0, 0.35),
    inset 0 0 0 1px rgba(0, 0, 0, 0.25);
  background: transparent;
  cursor: grab;
  z-index: 2;
}

.frame.dragging {
  cursor: grabbing;
}

.frame-label {
  position: absolute;
  left: 8px;
  top: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  pointer-events: none;
}

.preview-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.preview-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--theme--foreground-subdued);
}

.preview {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: var(--theme--border-radius);
  border: 1px solid var(--theme--border-color);
  background-color: #0b1f33;
}

.fallback-image {
  display: block;
  width: 100%;
  max-height: 240px;
  object-fit: contain;
  border-radius: var(--theme--border-radius);
  border: 1px solid var(--theme--border-color);
}
</style>
