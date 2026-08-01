#!/usr/bin/env node
/**
 * Converts stored article bodies from Markdown to HTML, so they can be edited in the Directus
 * WYSIWYG (`input-rich-text-html`) without being flattened on first save.
 *
 * Why this is safe to run on production content:
 *
 *   The public site renders a Markdown body as `sanitize(markdownIt.render(source))`. This
 *   script stores exactly `markdownIt.render(source)` — same markdown-it version, same options —
 *   and the site then renders an HTML body as `sanitize(source)`. The sanitize step, the URL
 *   rewriting and the final DOM are therefore unchanged: the conversion is a visual no-op.
 *
 * It is also idempotent (a body that already looks like HTML is skipped) and reversible
 * (every previous value is written to a backup file before anything is PATCHed; feed that file
 * to restore.mjs to undo).
 *
 * Usage:
 *     node convert.mjs --dry-run
 *     node convert.mjs --limit 10
 *     node convert.mjs
 *     node restore.mjs backup.<host>.<timestamp>.json
 */

import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import MarkdownIt from 'markdown-it'
import { connect, env, parseArgs } from './directus.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))

/** Collections whose `content` / `contentEn` hold a body. */
const COLLECTIONS = ['articles', 'events', 'programmes']

const BODY_FIELDS = ['content', 'contentEn']

/**
 * Must stay identical to the frontend:
 * knpu-university-fe/app/utils/renderStoredArticleMarkdown.ts
 */
const md = new MarkdownIt({ html: true, linkify: true, typographer: false })

/**
 * Must stay identical to `looksLikeHtmlBody` in
 * knpu-university-fe/app/utils/articleRichTextNormalize.ts — if converted output does not match
 * this, the site would feed it back through markdown-it.
 */
const HTML_BODY_RE
  = /^\s*<(?:p|div|h[1-6]|ul|ol|dl|table|figure|blockquote|pre|img|hr|section|article)[\s/>]/i

/**
 * Some imported content contains JSON-escaped newlines as literal text. The frontend un-escapes
 * them before rendering (`normalizeStoredMarkdownString`), so conversion must too.
 */
function normalizeStoredMarkdown(value) {
  const trimmed = value.trim()
  if (!trimmed) return ''
  const hasRealLineBreak = /[\r\n]/.test(trimmed)
  const hasEscapedLineBreak = /\\r\\n|\\n|\\r/.test(trimmed)
  if (!hasRealLineBreak && hasEscapedLineBreak) {
    return trimmed.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\r/g, '\n')
  }
  return trimmed
}

/** 'html' | 'markdown' | 'empty' | 'blocks' — only 'markdown' is converted. */
function classify(value) {
  if (value === null || value === undefined) return 'empty'
  if (Array.isArray(value) || typeof value === 'object') return 'blocks'
  if (typeof value !== 'string') return 'blocks'
  const normalized = normalizeStoredMarkdown(value)
  if (!normalized) return 'empty'
  return HTML_BODY_RE.test(normalized) ? 'html' : 'markdown'
}

function main() {
  const args = parseArgs(process.argv.slice(2))
  const collection = args.collection ?? 'articles'
  if (!COLLECTIONS.includes(collection)) {
    console.error(`! unknown collection ${collection} (expected one of ${COLLECTIONS.join(', ')})`)
    return 2
  }

  return run({
    collection,
    dryRun: Boolean(args['dry-run']),
    limit: args.limit ? Number(args.limit) : 0,
    url: args.url ?? env('DIRECTUS_URL', 'http://localhost:8055'),
    token: args.token ?? env('DIRECTUS_TOKEN'),
    email: args.email ?? env('DIRECTUS_EMAIL', 'admin@example.com'),
    password: args.password ?? env('DIRECTUS_PASSWORD', 'admin'),
    backupPath: args.out,
  })
}

async function run(options) {
  const { api, email } = await connect(options)
  console.error(`Directus ${options.url} as ${email}; collection '${options.collection}'`)

  const fields = ['id', 'slug', ...BODY_FIELDS].join(',')
  const { data: rows } = await api.get(
    `/items/${options.collection}?fields=${fields}&limit=-1&sort=id`,
  )
  const items = options.limit ? rows.slice(0, options.limit) : rows

  const backup = []
  const updates = []
  const counts = { markdown: 0, html: 0, empty: 0, blocks: 0 }
  const undetectable = []

  for (const item of items) {
    const patch = {}
    const previous = {}

    for (const field of BODY_FIELDS) {
      const kind = classify(item[field])
      counts[kind] += 1
      if (kind !== 'markdown') continue

      const source = normalizeStoredMarkdown(item[field])
      const html = md.render(source).trim()
      if (!HTML_BODY_RE.test(html)) {
        // Would be re-parsed as markdown by the site; leave it alone and report it.
        undetectable.push(`${item.slug ?? item.id}.${field}`)
        continue
      }
      patch[field] = html
      previous[field] = item[field]
    }

    if (Object.keys(patch).length === 0) continue
    backup.push({ id: item.id, slug: item.slug, ...previous })
    updates.push({ id: item.id, slug: item.slug, patch })
  }

  console.error(
    `${items.length} rows scanned · markdown=${counts.markdown} html=${counts.html} `
    + `empty=${counts.empty} blocks=${counts.blocks}`,
  )
  if (undetectable.length) {
    console.error(
      `! ${undetectable.length} field(s) skipped — converted output does not start with a block `
      + `tag: ${undetectable.slice(0, 10).join(', ')}`,
    )
  }

  if (updates.length === 0) {
    console.error('Nothing to convert.')
    return 0
  }

  if (options.dryRun) {
    for (const [index, update] of updates.entries()) {
      const preview = Object.entries(update.patch)
        .map(([field, html]) => `${field}: ${html.length} chars`)
        .join(', ')
      console.log(`[${index + 1}/${updates.length}] would convert ${update.slug ?? update.id} (${preview})`)
    }
    console.error(`\nDry run — ${updates.length} row(s) would change. Nothing was written.`)
    return 0
  }

  // Backup first: this file is the only way back.
  const host = new URL(options.url).hostname.replace(/[^a-z0-9.-]/gi, '_')
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const backupPath = options.backupPath ?? join(HERE, `backup.${host}.${stamp}.json`)
  writeFileSync(
    backupPath,
    `${JSON.stringify({ collection: options.collection, url: options.url, items: backup }, null, 2)}\n`,
    'utf8',
  )
  console.error(`Backup of ${backup.length} row(s) → ${backupPath}`)

  let done = 0
  for (const update of updates) {
    await api.request('PATCH', `/items/${options.collection}/${update.id}`, update.patch)
    done += 1
    if (done % 25 === 0) console.error(`  … ${done}/${updates.length}`)
  }

  console.error(`\nDone. converted=${done}  restore with: node restore.mjs ${backupPath}`)
  return 0
}

try {
  process.exitCode = (await main()) ?? 0
}
catch (error) {
  console.error(`! ${error.message ?? error}`)
  process.exitCode = 2
}
