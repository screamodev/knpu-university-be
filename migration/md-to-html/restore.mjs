#!/usr/bin/env node
/**
 * Undoes convert.mjs: writes the bodies stored in a backup file back to Directus.
 *
 * Usage:
 *     node restore.mjs backup.hnpu-admin.dev42hub.uk.2026-08-01T10-00-00-000Z.json
 *     node restore.mjs --dry-run backup.….json
 *
 * The backup records the URL it came from; restoring against a different instance needs an
 * explicit --url, because item ids do not match across environments.
 */

import { readFileSync } from 'node:fs'
import { connect, env, parseArgs } from './directus.mjs'

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const path = args._[0] ?? args.in
  if (!path) {
    console.error('! usage: node restore.mjs <backup.json> [--dry-run] [--url …]')
    return 2
  }

  const backup = JSON.parse(readFileSync(path, 'utf8'))
  const url = args.url ?? env('DIRECTUS_URL', backup.url)

  if (url !== backup.url && !args.url) {
    console.error(`! backup was taken from ${backup.url} but DIRECTUS_URL is ${url}.`)
    console.error('  Item ids differ between environments — pass --url explicitly to override.')
    return 2
  }

  const { api, email } = await connect({
    url,
    token: args.token ?? env('DIRECTUS_TOKEN'),
    email: args.email ?? env('DIRECTUS_EMAIL', 'admin@example.com'),
    password: args.password ?? env('DIRECTUS_PASSWORD', 'admin'),
  })
  console.error(`Directus ${url} as ${email}; restoring '${backup.collection}' from ${path}`)

  let done = 0
  for (const item of backup.items) {
    const { id, slug, ...fields } = item
    if (args['dry-run']) {
      console.log(`would restore ${slug ?? id}: ${Object.keys(fields).join(', ')}`)
      continue
    }
    await api.request('PATCH', `/items/${backup.collection}/${id}`, fields)
    done += 1
    if (done % 25 === 0) console.error(`  … ${done}/${backup.items.length}`)
  }

  console.error(
    args['dry-run']
      ? `\nDry run — ${backup.items.length} row(s) would be restored.`
      : `\nDone. restored=${done}`,
  )
  return 0
}

try {
  process.exitCode = (await main()) ?? 0
}
catch (error) {
  console.error(`! ${error.message ?? error}`)
  process.exitCode = 2
}
