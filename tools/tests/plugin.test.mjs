/**
 * Unit tests for the packaged skill provider.
 *
 * The plugin entry is deliberately independent of the Cordis runtime at its
 * boundary: these tests hand it a minimal context shape so the catalog parsing,
 * candidate contract, and prompt section can be checked without booting a
 * profile.
 */
import assert from 'node:assert/strict'
import test from 'node:test'
import { Writable } from 'node:stream'
import { apply, inject, name, serveViews } from '../../lib/index.js'

function harness(options = {}) {
  let provider
  const sections = []
  const routes = []
  const ctx = {
    skills: {
      registerProvider(factory) {
        provider = factory({ signal: new AbortController().signal, invalidate() {} })
        return () => {}
      },
    },
    systemPrompt: {
      section(section) {
        sections.push(section)
        return () => {}
      },
    },
    get(key) {
      if (key === 'webServer' && options.webServer) return options.webServer
      return undefined
    },
    webServer: options.webServer,
    inject(names, callback) {
      if (options.webServer) callback({ webServer: options.webServer })
      return { then() {} }
    },
  }
  apply(ctx)
  return { provider, sections, routes }
}

/** Minimal ServerResponse stand-in that records status, headers and body. */
function fakeResponse() {
  const chunks = []
  const res = new Writable({
    write(chunk, _encoding, callback) {
      chunks.push(Buffer.from(chunk))
      callback()
    },
  })
  res.statusCode = 0
  res.headers = {}
  res.writeHead = (code, headers = {}) => {
    res.statusCode = code
    Object.assign(res.headers, headers)
  }
  res.body = () => Buffer.concat(chunks)
  return res
}

/** Run one request through the static handler and wait for the response end. */
function request(url, method = 'GET') {
  const res = fakeResponse()
  const req = { method, url }
  const done = new Promise((resolve) => {
    res.on('finish', resolve)
    res.on('close', resolve)
  })
  serveViews(req, res)
  return done.then(() => res)
}

test('declares the plugin identity expected by the bundle patch', () => {
  assert.equal(name, 'cnjobs')
  assert.deepEqual(inject, ['skills', 'systemPrompt'])
})

test('registers one provider serving the packaged skills', () => {
  const { provider } = harness()
  assert.ok(provider, 'apply() should register a skill provider')
  assert.equal(provider.name, 'cnjobs')
  const skills = provider.list()
  assert.ok(Array.isArray(skills))
  assert.equal(skills.length, 8)
  assert.deepEqual(
    skills.map((skill) => skill.name).sort(),
    [
      'compose-profile',
      'find-channels',
      'find-incumbents',
      'find-investors',
      'find-person',
      'find-startups',
      'map-sectors',
      'setup-workspace',
    ],
  )
})

test('every candidate satisfies the registry contract', () => {
  const { provider } = harness()
  for (const skill of provider.list()) {
    assert.match(skill.name, /^[a-z0-9]+(?:-[a-z0-9]+)*$/)
    assert.equal(typeof skill.description, 'string')
    assert.ok(skill.description.length > 0)
    assert.equal(skill.provider, 'cnjobs')
    assert.equal(skill.source, 'bundled')
    assert.equal(skill.rank, 600)
    assert.deepEqual(skill.invocation, { modelInvocable: true, userInvocable: true })
    assert.equal(typeof skill.path, 'string')
    assert.ok(skill.path.endsWith('SKILL.md'))
    assert.equal(skill.resourceBase.kind, 'directory')
    assert.ok(skill.resourceBase.path.endsWith(skill.name))
    assert.equal(skill.metadata.package, 'cnjobs')
  }
})

test('loads a body without the frontmatter and keeps the directory resource base', () => {
  const { provider } = harness()
  const candidate = provider.list().find((skill) => skill.name === 'find-person')
  const loaded = provider.get(candidate)
  assert.equal(loaded.name, 'find-person')
  assert.equal(loaded.provider, 'cnjobs')
  assert.ok(!loaded.content.startsWith('---'), 'frontmatter must be stripped')
  assert.ok(loaded.content.includes('Find Person'), 'body must be the skill instructions')
  assert.equal(loaded.resourceBase.path, candidate.resourceBase.path)
})

test('adds one rooted prompt section naming the installed framework', () => {
  const { sections } = harness()
  assert.equal(sections.length, 1)
  const [section] = sections
  assert.equal(section.name, 'plugin:cnjobs')
  assert.equal(section.order, 190)
  assert.ok(section.text.includes('/skills/') === false, 'section is prose, not a path dump')
  assert.ok(section.text.includes('cnjobs is installed at'))
  assert.ok(section.text.includes('data/companies/*.json'))
  assert.ok(section.text.includes('tools/build.py'))
  assert.ok(!section.text.includes('{{'), 'prompt variables must stay unresolved-free')
})

test('mounts the dashboard route only when the Web surface provides a server', () => {
  const registered = []
  const webServer = {
    register(route) {
      registered.push(route)
      return () => {}
    },
  }
  harness({ webServer })
  assert.equal(registered.length, 1)
  assert.equal(registered[0].kind, 'prefix')
  assert.equal(registered[0].path, '/cnjobs')
  assert.equal(typeof registered[0].handler, 'function')

  const headless = harness()
  assert.equal(headless.provider.name, 'cnjobs', 'headless profiles still get the skills')
})

test('serves the generated dashboard and its logo assets', async () => {
  const page = await request('/cnjobs/dashboard.html')
  assert.equal(page.statusCode, 200)
  assert.match(page.headers['content-type'], /^text\/html/)
  assert.match(page.body().toString('utf8'), /<title>/)

  const icon = await request('/cnjobs/assets/logos/deepseek.ico')
  assert.equal(icon.statusCode, 200)
  assert.equal(icon.headers['content-type'], 'image/x-icon')
  assert.ok(icon.body().length > 0)
})

test('redirects the bare mount point and refuses to leave the views root', async () => {
  const root = await request('/cnjobs/')
  assert.equal(root.statusCode, 302)
  assert.equal(root.headers.location, '/cnjobs/dashboard.html')

  const missing = await request('/cnjobs/missing.html')
  assert.equal(missing.statusCode, 404)

  // A dot-dot segment survives URL parsing only when its slash is encoded.
  const escaped = await request('/cnjobs/..%2fpackage.json')
  assert.equal(escaped.statusCode, 403)
  // A plain ../ is normalized away by the URL parser; the request must still
  // never reach a package file outside the views root.
  const normalized = await request('/cnjobs/%2e%2e/package.json')
  assert.ok([403, 404].includes(normalized.statusCode))

  const badMethod = await request('/cnjobs/dashboard.html', 'POST')
  assert.equal(badMethod.statusCode, 405)

  const head = await request('/cnjobs/dashboard.html', 'HEAD')
  assert.equal(head.statusCode, 200)
  assert.equal(head.body().length, 0)
})
