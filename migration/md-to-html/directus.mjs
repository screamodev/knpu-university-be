/**
 * Minimal Directus REST client shared by convert.mjs and restore.mjs.
 *
 * Deliberately dependency-free apart from markdown-it: this runs against production, and the
 * fewer moving parts between here and the database, the better.
 */

/**
 * Production sits behind Cloudflare, which answers "error code: 1010" (banned browser
 * signature) to the default Node fetch UA. Presenting normal browser headers clears it.
 * Same fix as migration/legacy-news/3_load.py.
 */
export const BROWSER_HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    + '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
  'Accept': 'application/json, text/plain, */*',
  'Accept-Language': 'en-US,en;q=0.9,uk;q=0.8',
}

export class DirectusError extends Error {}

/** `-e VAR=$UNSET` passes an *empty* value, so treat blank as unset. */
export function env(name, fallback = undefined) {
  const value = (process.env[name] ?? '').trim()
  return value || fallback
}

export class Directus {
  constructor(baseUrl, token) {
    this.base = baseUrl.replace(/\/$/, '')
    this.token = token
  }

  async request(method, path, payload) {
    const headers = { ...BROWSER_HEADERS, Authorization: `Bearer ${this.token}` }
    const init = { method, headers }
    if (payload !== undefined) {
      headers['Content-Type'] = 'application/json'
      init.body = JSON.stringify(payload)
    }

    const response = await fetch(`${this.base}${path}`, init)
    const body = await response.text()
    if (!response.ok) {
      throw new DirectusError(`${method} ${path} → HTTP ${response.status}: ${body.slice(0, 500)}`)
    }
    return body ? JSON.parse(body) : {}
  }

  get(path) {
    return this.request('GET', path)
  }
}

export async function login(baseUrl, email, password) {
  const response = await fetch(`${baseUrl.replace(/\/$/, '')}/auth/login`, {
    method: 'POST',
    headers: { ...BROWSER_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const body = await response.text()
  if (!response.ok) {
    throw new DirectusError(`login failed: HTTP ${response.status} ${body.slice(0, 200)}`)
  }
  return JSON.parse(body).data.access_token
}

/** Resolves auth from flags/env and verifies it, with a readable message when it fails. */
export async function connect({ url, token, email, password }) {
  if (!/^https?:\/\//.test(url ?? '')) {
    throw new DirectusError(
      `DIRECTUS_URL is ${JSON.stringify(url)} — it must start with http:// or https://\n`
      + '  If you passed -e DIRECTUS_URL=$PROD_URL, that variable is empty in this shell.',
    )
  }

  try {
    const accessToken = token || (await login(url, email, password))
    const api = new Directus(url, accessToken)
    const me = await api.get('/users/me?fields=email')
    return { api, email: me.data.email }
  }
  catch (error) {
    const message = String(error)
    throw new DirectusError(
      `Could not authenticate against ${url}\n  ${message}\n`
      + (message.includes('error code: 1010')
        ? '  This is Cloudflare, not Directus: code 1010 = blocked browser signature.\n'
        : '')
      + '  Check: echo $DIRECTUS_URL $DIRECTUS_TOKEN — and that the token can read/write articles.',
    )
  }
}

/** Parses `--flag value` / `--flag` argv into an object. */
export function parseArgs(argv) {
  const args = {}
  const positional = []
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i]
    if (!token.startsWith('--')) {
      positional.push(token)
      continue
    }
    const name = token.slice(2)
    const next = argv[i + 1]
    if (next === undefined || next.startsWith('--')) {
      args[name] = true
    }
    else {
      args[name] = next
      i += 1
    }
  }
  args._ = positional
  return args
}
