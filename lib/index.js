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
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
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
 * Apply the plugin: register the packaged skill provider and the root note.
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
}
