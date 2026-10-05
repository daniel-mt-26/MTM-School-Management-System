import assert from 'node:assert/strict'
import { after, afterEach, test } from 'node:test'
import React from 'react'
import { JSDOM } from 'jsdom'
import { transformWithOxc } from 'vite'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { Buffer } from 'node:buffer'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' })
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.IS_REACT_ACT_ENVIRONMENT = true
dom.window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
const { render, fireEvent, screen, waitFor, cleanup } = await import('@testing-library/react')
const source = await readFile(new URL('./FeeRecordActions.jsx', import.meta.url), 'utf8')
const transformed = await transformWithOxc(source, 'FeeRecordActions.jsx', { jsx: { runtime: 'automatic' } })
const require = createRequire(import.meta.url)
const code = transformed.code.replace(/from (["'])(react(?:\/jsx-runtime)?)\1/g, (_, quote, name) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
const { default: FeeRecordActions } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const record = { id: 7, name: 'Mistaken fee', amount: '75.00', currency: 'USD', is_active: true, can_delete: true }
const props = { record, onDelete: async () => {}, onDeactivate: async () => {}, onDeleted: () => {} }
afterEach(cleanup)
after(() => dom.window.close())

test('unused fees and templates require confirmation; cancel makes no request', () => {
  for (const recurring of [false, true]) {
    let calls = 0
    render(React.createElement(FeeRecordActions, { ...props, recurring, onDelete: () => { calls++ } }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))
    assert.ok(screen.getByRole('dialog'))
    assert.ok(screen.getByText(recurring ? 'Delete recurring fee permanently?' : 'Delete this fee permanently?'))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    assert.equal(Boolean(screen.queryByRole('dialog')), false)
    assert.equal(calls, 0)
    cleanup()
  }
})

test('successful deletion removes the record from the list', async () => {
  let calls = 0
  function List() {
    const [items, setItems] = React.useState([record])
    return items.map((item) => React.createElement(FeeRecordActions, { ...props, key: item.id, record: item,
      onDelete: async (id) => { assert.equal(id, 7); calls++ },
      onDeleted: (id) => setItems((old) => old.filter((x) => x.id !== id)),
    }))
  }
  render(React.createElement(List))
  fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))
  fireEvent.click(screen.getAllByRole('button', { name: 'Delete permanently' }).at(-1))
  await waitFor(() => assert.equal(Boolean(screen.queryByRole('button', { name: 'Deactivate' })), false))
  assert.equal(calls, 1)
})

test('a stale eligibility hint cannot hide the backend rejection', async () => {
  let removed = false
  render(React.createElement(FeeRecordActions, { ...props,
    onDelete: async () => { throw { data: { detail: 'Financial records already exist. Deactivate it instead.' } } },
    onDeleted: () => { removed = true },
  }))
  fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))
  fireEvent.click(screen.getAllByRole('button', { name: 'Delete permanently' }).at(-1))
  await waitFor(() => assert.match(screen.getByRole('alert').textContent, /Financial records already exist/))
  assert.equal(removed, false)
  assert.ok(screen.getByRole('dialog'))
})

test('used fees hide permanent deletion while deactivation remains independent', async () => {
  const changes = []
  render(React.createElement(FeeRecordActions, { ...props, record: { ...record, can_delete: false },
    onDeactivate: async (...args) => changes.push(args),
  }))
  assert.equal(Boolean(screen.queryByRole('button', { name: 'Delete permanently' })), false)
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }))
  await waitFor(() => assert.deepEqual(changes, [[7, false]]))
  assert.equal(Boolean(screen.queryByRole('dialog')), false)
})
