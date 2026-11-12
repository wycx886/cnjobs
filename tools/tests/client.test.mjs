/**
 * Tests for the browser half (`lib/client.js`).
 *
 * The module is a loader script, not an ESM import target, so the test stubs
 * the `window.__ModuleLoader__` bootstrap, materializes the factory with a
 * minimal `react`, and drives the slot registrations by hand.
 */
import assert from 'node:assert/strict'
import test from 'node:test'

const react = {
  createElement(type, props, ...children) {
    return { type, props: props ?? {}, children }
  },
}

/** Load the client bundle the way the Web shell's loader does. */
async function loadClient() {
  let record
  globalThis.window = {
    __ModuleLoader__: {
      load(entry) {
        record = entry
      },
    },
  }
  // A unique query keeps Node from reusing the module instance between tests.
  await import(`../../lib/client.js?run=${Math.random().toString(36).slice(2)}`)
  assert.ok(record, 'the bundle must register itself with the module loader')
  assert.equal(record.id, 'cnjobs')
  return record.factory((specifier) => {
    if (specifier === 'react') return react
    throw new Error(`unexpected require: ${specifier}`)
  })
}

test('registers a sidebar row, its page and a view tab', async () => {
  const mod = await loadClient()
  assert.equal(mod.name, 'cnjobs')
  assert.deepEqual(mod.inject, ['slots'])

  const registrations = []
  const ctx = {
    slots: {
      inject(_name, callback) {
        callback()
      },
      register(meta, render) {
        registrations.push({ meta, render })
        return () => {}
      },
    },
  }
  mod.apply(ctx)
  assert.equal(registrations.length, 3)

  const row = registrations.find((entry) => entry.meta.name === 'sidebar.panellist')
  assert.ok(row, 'must add a left-sidebar navigation row')
  assert.equal(row.meta.id, 'cnjobs')
  assert.equal(row.meta.order, 40)
  assert.equal(row.meta.label(), 'CN Jobs')

  const page = registrations.find((entry) => entry.meta.name === 'main')
  assert.ok(page, 'must route the main column for that panel key')
  assert.equal(page.meta.key, 'cnjobs')

  const view = registrations.find((entry) => entry.meta.name === 'conversation.view')
  assert.ok(view, 'must add a conversation view tab')
  assert.equal(view.meta.id, 'cnjobs-dashboard')
  assert.equal(view.meta.order, 30)
})

test('the sidebar page and the view tab render the dashboard iframe', async () => {
  const mod = await loadClient()
  const registrations = []
  mod.apply({
    slots: {
      inject(_name, callback) {
        callback()
      },
      register(meta, render) {
        registrations.push({ meta, render })
      },
    },
  })
  const view = registrations.find((entry) => entry.meta.name === 'conversation.view')
  const page = registrations.find((entry) => entry.meta.name === 'main')
  const pageWrapper = page.render({})
  const pageElement = pageWrapper.type(pageWrapper.props)
  assert.equal(pageElement.type, 'div')
  assert.equal(pageElement.children[0].props.src, '/cnjobs/dashboard.html')

  const wrapper = view.render({})
  const element = wrapper.type(wrapper.props)
  assert.equal(element.type, 'div')
  const iframe = element.children[0]
  assert.equal(iframe.type, 'iframe')
  assert.equal(iframe.props.src, '/cnjobs/dashboard.html')
  assert.equal(iframe.props.style.width, '100%')
})
