/**
 * cnjobs — DeepSeek Harness plugin entry.
 *
 * The package ships the whole opportunity-research framework: the eight
 * methodology skills under `skills/`, the canonical dataset under `data/`, and
 * the Python tooling under `tools/`. This module does two things:
 *
 * 1. registers a read-only skill provider rooted at this package's `skills/`
 *    directory, so every installed profile sees the skills without copying or
 *    symlinking anything into `$DSH_HOME/skills`;
 * 2. contributes one short system-prompt section naming the package root, so a
 *    loaded skill's relative paths (`data/companies/…`, `tools/build.py`) always
 *    resolve against the installed copy instead of the user's working directory.
 *
 * The plugin is deliberately dependency-free and side-effect-free: no network,
 * no writes, no profile edits.
 */
import { createReadStream, readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = 'cnjobs'
export const inject = ['skills', 'systemPrompt']

/** Provider label shown in skill metadata and diagnostics. */
const PROVIDER = 'cnjobs'
/** Packaged-provider rank: lower than project/user roots so those still win. */
const RANK = 600
/** Section order inside the tool-guidance band (100–199). */
const SECTION_ORDER = 190

const PKG_ROOT = fileURLToPath(new URL('..', import.meta.url))
const SKILLS_DIR = join(PKG_ROOT, 'skills')
/** Generated reading views (dashboard, Markdown, logo assets) served to the Web UI. */
const VIEWS_ROOT = join(PKG_ROOT, 'data', 'views')
/** Public mount point of the dashboard inside the Web UI origin. */
const DASHBOARD_PREFIX = '/cnjobs'
const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
}
const IS_KEBAB = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

/** Parse the leading YAML frontmatter of a SKILL.md file. */
function parseFrontmatter(text) {
  if (!text.startsWith('---')) return undefined
  const end = text.indexOf('\n---', 3)
  if (end < 0) return undefined
  const header = text.slice(3, end)
  const bodyStart = text.indexOf('\n', end + 1)
  const body = bodyStart < 0 ? '' : text.slice(bodyStart + 1)
  const data = {}
  let key = null
  for (const line of header.split('\n')) {
    if (line.trim().length === 0) continue
    if (/^\s/.test(line)) {
      if (key !== null) data[key] = `${data[key]} ${line.trim()}`.trim()
      continue
    }
    const match = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line)
    if (match === null) continue
    key = match[1]
    let value = match[2].trim()
    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1)
    }
    if (/^[>|][+-]?$/.test(value)) value = ''
    data[key] = value
  }
  return { data, body }
}

/** Interpret the invocation-policy booleans accepted by skill frontmatter. */
function readBoolean(value, fallback) {
  if (value === undefined) return fallback
  const normalized = String(value).trim().toLowerCase()
  if (['true', 'yes', 'on', '1'].includes(normalized)) return true
  if (['false', 'no', 'off', '0'].includes(normalized)) return false
  return fallback
}

/** Read one directory-bundle skill, or `undefined` when it is not a skill. */
function readSkillBundles() {
  let entries
  try {
    entries = readdirSync(SKILLS_DIR, { withFileTypes: true })
  } catch {
    return []
  }
  const skills = []
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const directory = join(SKILLS_DIR, entry.name)
    const path = join(directory, 'SKILL.md')
    try {
      if (!statSync(path).isFile()) continue
    } catch {
      continue
    }
    const parsed = parseFrontmatter(readFileSync(path, 'utf8'))
    if (parsed === undefined) continue
    const skillName = String(parsed.data.name ?? '').trim()
    const description = String(parsed.data.description ?? '').trim()
    if (!IS_KEBAB.test(skillName) || description.length === 0) continue
    const whenToUse = String(parsed.data.whenToUse ?? '').trim()
    skills.push({
      name: skillName,
      description,
      ...(whenToUse.length > 0 ? { whenToUse } : {}),
      invocation: {
        modelInvocable: readBoolean(parsed.data['disable-model-invocation'], false) === false,
        userInvocable: readBoolean(parsed.data['user-invocable'], true) === true,
      },
      source: 'bundled',
      provider: PROVIDER,
      rank: RANK,
      path,
      locator: path,
      resourceBase: { kind: 'directory', path: directory },
      metadata: { package: name, root: PKG_ROOT },
    })
  }
  return skills
}

/** Read-only skill provider over the packaged `skills/` directory. */
const provider = {
  name: PROVIDER,
  list() {
    return readSkillBundles()
  },
  get(candidate) {
    const path = candidate.locator
    let text
    try {
      text = readFileSync(path, 'utf8')
    } catch {
      return undefined
    }
    const parsed = parseFrontmatter(text)
    if (parsed === undefined) return undefined
    const whenToUse = String(parsed.data.whenToUse ?? '').trim()
    return {
      ...candidate,
      ...(whenToUse.length > 0 ? { whenToUse } : {}),
      content: parsed.body,
    }
  },
}

/** Root note: keep packaged paths anchored to the installed copy. */
function rootSection() {
  const skills = readSkillBundles()
    .map((skill) => skill.name)
    .sort()
    .join(', ')
  return [
    `${name} is installed at ${PKG_ROOT}.`,
    'It ships a China AI opportunity-research framework: methodology skills, the canonical public dataset (`data/companies/*.json`, `data/lists/`, `data/taxonomy.json`, `data/schemas/`), and Python tools under `tools/`.',
    `Bundled skills: ${skills}.`,
    'When a skill mentions a repository-relative path (`data/…`, `tools/…`, `skills/…`), resolve it against this root and run tools from there (for example `python3 tools/build.py`).',
    'Never hand-edit generated output (`data/index.json`, `data/views/*`); regenerate it with the build tool.',
    'Private job-search material (résumé, applications, chat records) belongs to the user\'s own private workspace, never to a public data file or to this plugin directory.',
  ].join('\n')
}

/**
 * Serve one file of the generated reading views.
 *
 * The whole `data/views/` tree is published under {@link DASHBOARD_PREFIX} so the
 * dashboard keeps working with its relative logo and asset URLs. Requests are
 * resolved inside that root only, so a crafted path cannot escape the package.
 *
 * @param {import('node:http').IncomingMessage} req - the HTTP request.
 * @param {import('node:http').ServerResponse} res - the HTTP response.
 */
export function serveViews(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { allow: 'GET, HEAD' })
    res.end()
    return
  }
  let pathname
  try {
    pathname = decodeURIComponent(new URL(req.url ?? '/', 'http://127.0.0.1').pathname)
  } catch {
    res.writeHead(400)
    res.end()
    return
  }
  if (pathname === DASHBOARD_PREFIX || pathname === `${DASHBOARD_PREFIX}/`) {
    res.writeHead(302, { location: `${DASHBOARD_PREFIX}/dashboard.html` })
    res.end()
    return
  }
  const relative = pathname.slice(DASHBOARD_PREFIX.length + 1)
  const target = resolve(VIEWS_ROOT, relative)
  if (target !== VIEWS_ROOT && !target.startsWith(VIEWS_ROOT + sep)) {
    res.writeHead(403)
    res.end()
    return
  }
  let stats
  try {
    stats = statSync(target)
  } catch {
    res.writeHead(404)
    res.end()
    return
  }
  if (!stats.isFile()) {
    res.writeHead(404)
    res.end()
    return
  }
  const type = CONTENT_TYPES[extname(target).toLowerCase()] ?? 'application/octet-stream'
  res.writeHead(200, {
    'content-type': type,
    'content-length': stats.size,
    'cache-control': 'no-cache',
    'x-content-type-options': 'nosniff',
  })
  if (req.method === 'HEAD') {
    res.end()
    return
  }
  createReadStream(target)
    .on('error', () => res.destroy())
    .pipe(res)
}

/**
 * Apply the plugin: packaged skills, the root note, and (on the Web surface) the
 * dashboard route behind the client tab.
 * @param {import('@deepseek-ai/cordis').Context} ctx - the Cordis context.
 */
export function apply(ctx) {
  // A single provider registration per fiber; the registry keeps it in the
  // calling scope's layer and disposes it with the fiber.
  ctx.skills.registerProvider(() => provider)
  ctx.systemPrompt.section({
    name: 'plugin:cnjobs',
    order: SECTION_ORDER,
    text: rootSection(),
  })

  // The HTTP carrier only exists on the Web surface (browser or desktop host).
  // Mounting is deferred through `ctx.inject` instead of reading `ctx.webServer`
  // directly: a direct read requires that service in the plugin's own `inject`,
  // which would then keep the whole plugin inactive on headless profiles that
  // never provide it. Here headless profiles simply never run the callback.
  // Returning the route's disposer lets Cordis unmount it with this fiber, so a
  // profile reload does not leave a dead handler on the old server.
  ctx.inject(['webServer'], (scoped) =>
    scoped.webServer.register({ kind: 'prefix', path: DASHBOARD_PREFIX, handler: serveViews }),
  )
}
