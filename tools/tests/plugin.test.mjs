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
import { apply, inject, name } from '../../lib/index.js'

function harness() {
  let provider
  const sections = []
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
  }
  apply(ctx)
  return { provider, sections }
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
