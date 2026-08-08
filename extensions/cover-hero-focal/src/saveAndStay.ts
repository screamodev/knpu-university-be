/**
 * Directus 11 primary checkmark = saveAndQuit (navigate back to collection).
 * Remap it to the built-in Save and Stay action via SaveOptions (⋮ more_vert).
 *
 * Native `default_save_action` exists only from Directus 12.2+.
 */

const MENU_OUTLET = '#menu-outlet'

let pendingSaveAndStay = false
let menuObserver: MutationObserver | null = null
let listening = false
let refCount = 0

function isContentItemPath(): boolean {
  return /\/content\/[^/]+\/[^/]+\/?$/.test(window.location.pathname)
}

function isInsideMenu(el: Element): boolean {
  return Boolean(el.closest(MENU_OUTLET))
}

function findPrimarySaveButton(from: Element): HTMLElement | null {
  if (isInsideMenu(from)) return null

  const header = from.closest('header')
  if (!header) return null

  const button =
    from.closest<HTMLElement>('button') || from.closest<HTMLElement>('[role="button"]')

  if (!button || !header.contains(button)) return null
  if (!button.querySelector('[data-icon="check"]')) return null
  if (!findSaveOptionsActivator(button)) return null

  return button
}

function findSaveOptionsActivator(saveButton: HTMLElement): HTMLElement | null {
  let node: HTMLElement | null = saveButton.parentElement

  for (let depth = 0; depth < 4 && node; depth += 1) {
    const icons = node.querySelectorAll<HTMLElement>('[data-icon="more_vert"]')

    for (const icon of icons) {
      if (saveButton.contains(icon)) continue
      return icon.closest('button') || icon.closest('[role="button"]') || icon
    }

    node = node.parentElement
  }

  return null
}

function clickSaveAndStayInMenu(): boolean {
  const outlet = document.querySelector(MENU_OUTLET)
  if (!outlet) return false

  const items = outlet.querySelectorAll<HTMLElement>('.v-list-item, [role="menuitem"], li, button')

  for (const item of items) {
    const text = (item.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase()
    if (
      text.includes('save and stay') ||
      text.includes('зберегти і залишити') ||
      text.includes('зберегти та залишити') ||
      text.includes('сохранить и остаться')
    ) {
      item.click()
      return true
    }
  }

  for (const item of items) {
    if (item.querySelector('[data-icon="check"]')) {
      item.click()
      return true
    }
  }

  return false
}

function requestSaveAndStay(saveButton: HTMLElement): void {
  pendingSaveAndStay = true

  if (clickSaveAndStayInMenu()) {
    pendingSaveAndStay = false
    return
  }

  findSaveOptionsActivator(saveButton)?.click()

  window.setTimeout(() => {
    if (pendingSaveAndStay && clickSaveAndStayInMenu()) {
      pendingSaveAndStay = false
    }
  }, 30)

  window.setTimeout(() => {
    if (pendingSaveAndStay && clickSaveAndStayInMenu()) {
      pendingSaveAndStay = false
    }
  }, 120)

  window.setTimeout(() => {
    pendingSaveAndStay = false
  }, 400)
}

function onMenuMutated(): void {
  if (!pendingSaveAndStay) return
  if (clickSaveAndStayInMenu()) {
    pendingSaveAndStay = false
  }
}

function onClickCapture(event: MouseEvent): void {
  if (!isContentItemPath()) return

  const target = event.target
  if (!(target instanceof Element)) return
  if (target.closest('[data-icon="more_vert"]')) return

  const saveButton = findPrimarySaveButton(target)
  if (!saveButton) return
  if (saveButton.hasAttribute('disabled') || saveButton.getAttribute('aria-disabled') === 'true') {
    return
  }

  event.preventDefault()
  event.stopPropagation()
  event.stopImmediatePropagation()

  requestSaveAndStay(saveButton)
}

/** Manual trigger from the form (⋮ → Save and Stay), when the header remap is unavailable. */
export function triggerSaveAndStay(): boolean {
  if (!isContentItemPath()) return false

  const checks = document.querySelectorAll<HTMLElement>('header button [data-icon="check"], header [role="button"] [data-icon="check"]')

  for (const icon of checks) {
    if (isInsideMenu(icon)) continue
    const button = icon.closest<HTMLElement>('button') || icon.closest<HTMLElement>('[role="button"]')
    if (!button) continue
    if (!findSaveOptionsActivator(button)) continue
    requestSaveAndStay(button)
    return true
  }

  return false
}

export function installArticleSaveAndStay(): () => void {
  refCount += 1

  if (!listening) {
    listening = true
    document.addEventListener('click', onClickCapture, true)

    menuObserver = new MutationObserver(onMenuMutated)
    const outlet = document.querySelector(MENU_OUTLET)
    if (outlet) {
      menuObserver.observe(outlet, { childList: true, subtree: true })
    }
  }

  return () => {
    refCount = Math.max(0, refCount - 1)
    if (refCount > 0) return

    document.removeEventListener('click', onClickCapture, true)
    menuObserver?.disconnect()
    menuObserver = null
    pendingSaveAndStay = false
    listening = false
  }
}
