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

test('registers one view tab and one sidebar action', async () => {
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
  assert.equal(registrations.length, 2)

  const view = registrations.find((entry) => entry.meta.name === 'conversation.view')
  assert.ok(view, 'must add a conversation view tab')
  assert.equal(view.meta.id, 'cnjobs-dashboard')
  assert.equal(view.meta.order, 30)
  assert.equal(view.meta.label(), 'CN Jobs')

  const action = registrations.find((entry) => entry.meta.name === 'sidebar.footer.action')
  assert.ok(action, 'must add a sidebar action')
  assert.equal(action.meta.id, 'cnjobs-open')
})

test('the view renders the packaged dashboard in an iframe', async () => {
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
  const wrapper = view.render({})
  const element = wrapper.type(wrapper.props)
  assert.equal(element.type, 'div')
  const iframe = element.children[0]
  assert.equal(iframe.type, 'iframe')
  assert.equal(iframe.props.src, '/cnjobs/dashboard.html')
  assert.equal(iframe.props.style.width, '100%')
})
