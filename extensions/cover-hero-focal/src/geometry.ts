/**
 * Geometry for a hero-aspect crop window inside an image, keyed by focal point (frame center).
 */

export interface ImageSize {
  width: number
  height: number
}

export interface FrameRect {
  x: number
  y: number
  width: number
  height: number
}

export interface FocalPoint {
  x: number
  y: number
}

/** Matches the public article hero band at typical desktop width (~1280×512). */
export const DEFAULT_HERO_ASPECT_RATIO = 2.5

/** Largest rectangle of aspect `ratio` (w/h) that fits inside the image. */
export function maxFrameSize(image: ImageSize, ratio: number): { width: number; height: number } {
  const safeRatio = ratio > 0 ? ratio : DEFAULT_HERO_ASPECT_RATIO
  const imageRatio = image.width / image.height

  if (imageRatio >= safeRatio) {
    const height = image.height
    const width = height * safeRatio
    return { width, height }
  }

  const width = image.width
  const height = width / safeRatio
  return { width, height }
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function frameFromFocal(
  image: ImageSize,
  focal: FocalPoint,
  ratio: number,
): FrameRect {
  const size = maxFrameSize(image, ratio)
  const x = clamp(focal.x - size.width / 2, 0, image.width - size.width)
  const y = clamp(focal.y - size.height / 2, 0, image.height - size.height)
  return { x, y, width: size.width, height: size.height }
}

export function focalFromFrame(frame: FrameRect): FocalPoint {
  return {
    x: frame.x + frame.width / 2,
    y: frame.y + frame.height / 2,
  }
}

/** Default FE cover anchor when no focal point is saved: 50% / 35%. */
export function defaultFocal(image: ImageSize): FocalPoint {
  return {
    x: image.width * 0.5,
    y: image.height * 0.35,
  }
}

/**
 * CSS `object-position` so `object-fit: cover` shows `frame` when the box has the same aspect.
 *
 * Naive `focalX/width%` is wrong: it pins the focal point to that % of the box (near the top for
 * a top frame), clipping everything above the frame center. Travel along the freer axis maps the
 * rectangle instead.
 */
export function objectPositionFromFrame(image: ImageSize, frame: FrameRect): string {
  const travelX = image.width - frame.width
  const travelY = image.height - frame.height
  const left = travelX <= 0 ? 50 : clamp((frame.x / travelX) * 100, 0, 100)
  const top = travelY <= 0 ? 50 : clamp((frame.y / travelY) * 100, 0, 100)
  return `${left.toFixed(2)}% ${top.toFixed(2)}%`
}

export function objectPositionCss(
  image: ImageSize,
  focal: FocalPoint,
  ratio: number = DEFAULT_HERO_ASPECT_RATIO,
): string {
  return objectPositionFromFrame(image, frameFromFocal(image, focal, ratio))
}
