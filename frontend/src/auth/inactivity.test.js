import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { beginSession, INACTIVITY_MESSAGE, INACTIVITY_MS, monitorInactivity, publishLogout, sessionEndReason } from './inactivity.js'

const originals = Object.fromEntries(['window', 'document', 'localStorage', 'sessionStorage', 'setTimeout', 'clearTimeout'].map(key => [key, globalThis[key]]))
const realNow = Date.now
afterEach(() => { Object.assign(globalThis, originals); Date.now = realNow })

// Independent tab event targets and sessionStorage, shared localStorage, and a
// deterministic clock let us exercise trusted input and suspended browser timers.
function browser() {
  const shared = new Map(), tabs = [], timers = new Map()
  let now = 1000000, active, sequence = 0
  Date.now = () => now
  const storage = map => ({ getItem: key => map.get(key) ?? null, setItem: (key, value) => map.set(key, String(value)) })
  function target() {
    const listeners = new Map()
    return {
      addEventListener(name, fn) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn) },
      removeEventListener(name, fn) { listeners.get(name)?.delete(fn) },
      emit(name, event = {}) { for (const fn of listeners.get(name) || []) fn(event) },
      count() { return [...listeners.values()].reduce((sum, set) => sum + set.size, 0) },
    }
  }
  function run(tab, fn) {
    const previous = active
    active = tab
    Object.assign(globalThis, { window: tab.window, document: tab.document, sessionStorage: tab.storage, localStorage: tab.shared })
    try { return fn() } finally {
      active = previous
      if (previous) Object.assign(globalThis, { window: previous.window, document: previous.document, sessionStorage: previous.storage, localStorage: previous.shared })
    }
  }
  globalThis.setTimeout = (fn, delay) => { const id = ++sequence; timers.set(id, { fn, due: now + delay, tab: active }); return id }
  globalThis.clearTimeout = id => timers.delete(id)
  function tab(user) {
    const item = { user, window: target(), document: target(), storage: storage(new Map()), ended: [], warnings: [] }
    item.shared = {
      ...storage(shared),
      setItem(key, value) {
        const oldValue = shared.get(key) ?? null
        shared.set(key, String(value))
        if (oldValue === String(value)) return
        for (const other of tabs) if (other !== item) run(other, () => other.window.emit('storage', { key, newValue: String(value) }))
      },
    }
    tabs.push(item)
    item.run = fn => run(item, fn)
    item.start = () => item.run(() => {
      beginSession(user)
      item.stop = monitorInactivity(user, {
        onWarning: warning => item.warnings.push(warning),
        onEnd: reason => { item.ended.push(reason); if (!reason.id) publishLogout(user, reason.message, reason.preserveOfflineWork) },
      })
    })
    item.event = (name, trusted = true) => item.run(() => item.window.emit(name, { isTrusted: trusted }))
    return item
  }
  function advance(ms, suspended = false) {
    const end = now + ms
    if (!suspended) {
      while (true) {
        const entry = [...timers].filter(([, timer]) => timer.due <= end).sort((a, b) => a[1].due - b[1].due)[0]
        if (!entry) break
        const [id, timer] = entry
        timers.delete(id); now = Math.max(now, timer.due); run(timer.tab, timer.fn)
      }
    }
    now = end
  }
  return { tab, advance, timers, shared }
}

test('all four roles expire at exactly 600 seconds, once', () => {
  for (const role of ['platform_admin', 'school_admin', 'teacher', 'parent']) {
    const env = browser(), tab = env.tab({ id: 7, role })
    tab.start()
    env.advance(INACTIVITY_MS - 1)
    assert.equal(tab.ended.length, 0)
    assert.equal(env.timers.size, 1)
    assert.equal(tab.warnings.at(-1), true)
    env.advance(1)
    assert.equal(tab.ended.length, 1)
    assert.equal(tab.ended[0].message, INACTIVITY_MESSAGE)
    tab.event('focus'); tab.event('pointerdown'); env.advance(INACTIVITY_MS)
    assert.equal(tab.ended.length, 1)
    tab.run(tab.stop)
    assert.equal(tab.window.count() + tab.document.count(), 0)
    assert.equal(env.timers.size, 0)
  }
})

for (const event of ['pointerdown', 'click', 'keydown', 'scroll', 'touchstart', 'touchmove', 'wheel']) {
  test(`${event} resets the timer for a full ten minutes`, () => {
    const env = browser(), tab = env.tab({ id: 1, role: 'teacher' })
    tab.start(); env.advance(590000); tab.event(event)
    assert.equal(tab.warnings.at(-1), false)
    assert.equal(env.timers.size, 1)
    env.advance(599999); assert.equal(tab.ended.length, 0)
    env.advance(1); assert.equal(tab.ended.length, 1)
  })
}

test('synthetic events, polling and resume events cannot extend the deadline', () => {
  const env = browser(), tab = env.tab({ id: 1, role: 'teacher' })
  tab.start(); env.advance(590000)
  for (const event of ['pointerdown', 'click', 'keydown', 'scroll', 'touchstart']) tab.event(event, false)
  for (const event of ['focus', 'pageshow', 'poll', 'refresh']) tab.event(event)
  tab.run(() => tab.document.emit('visibilitychange'))
  env.advance(10000)
  assert.equal(tab.ended[0].message, INACTIVITY_MESSAGE)
})

for (const event of ['focus', 'pageshow', 'visibilitychange', 'pointerdown', 'keydown', 'touchstart', 'scroll']) {
  test(`return after suspended timers expires before ${event} can revive a session`, () => {
    const env = browser(), tab = env.tab({ id: 1, role: 'parent' })
    tab.start(); env.advance(INACTIVITY_MS + 1, true)
    if (event === 'visibilitychange') tab.run(() => tab.document.emit(event))
    else tab.event(event)
    assert.equal(tab.ended[0].message, INACTIVITY_MESSAGE)
    assert.equal(env.timers.size, 0)
  })
}

test('activity in either tab resets the shared deadline and logout reaches only the matching account', () => {
  const env = browser(), user = { id: 1, role: 'teacher' }
  const first = env.tab(user), second = env.tab(user), other = env.tab({ id: 2, role: 'teacher' })
  const otherRole = env.tab({ id: 1, role: 'parent' })
  first.start(); second.start(); other.start(); otherRole.start()
  env.advance(590000); first.event('keydown'); other.event('keydown'); otherRole.event('keydown')
  env.advance(590000); second.event('scroll'); other.event('keydown'); otherRole.event('keydown')
  assert.equal(first.ended.length + second.ended.length, 0)
  first.run(() => publishLogout(user, '', true))
  assert.equal(second.ended.length, 1)
  assert.equal(second.ended[0].message, '')
  assert.equal(other.ended.length, 0)
  assert.equal(otherRole.ended.length, 0)
})

test('inactivity logout propagates its message across tabs without rebroadcasting', () => {
  const env = browser(), user = { id: 1, role: 'school_admin' }
  const first = env.tab(user), second = env.tab(user)
  first.start(); second.start(); env.advance(INACTIVITY_MS)
  assert.equal(first.ended.length, 1); assert.equal(second.ended.length, 1)
  assert.equal(second.ended[0].message, INACTIVITY_MESSAGE)
  assert.equal(env.timers.size, 0)
})

test('a tab that missed the logout event rejects its stored session on return or reload', () => {
  const env = browser(), user = { id: 1, role: 'parent' }
  const first = env.tab(user), second = env.tab(user)
  first.start(); second.start(); second.run(second.stop)
  first.run(() => publishLogout(user, '', true))
  assert.equal(second.run(() => sessionEndReason(user)).message, '')
  // A fresh explicit login accepts the current logout version.
  second.run(() => beginSession(user))
  assert.equal(second.run(() => sessionEndReason(user)), null)
})

test('effect cleanup and restart keep one timer and one set of listeners', () => {
  const env = browser(), tab = env.tab({ id: 1, role: 'teacher' })
  tab.start()
  const count = tab.window.count() + tab.document.count()
  tab.run(tab.stop); tab.start()
  assert.equal(env.timers.size, 1)
  assert.equal(tab.window.count() + tab.document.count(), count)
  tab.run(tab.stop)
  assert.equal(env.timers.size, 0)
})

test('cleared or invalid shared activity ends the session without a repeated zero-delay timer', () => {
  for (const value of [null, 'invalid']) {
    const env = browser(), tab = env.tab({ id: 1, role: 'teacher' })
    tab.start()
    if (value === null) env.shared.delete('mtm:last-activity:1:teacher')
    else env.shared.set('mtm:last-activity:1:teacher', value)
    tab.run(() => tab.window.emit('storage', { key: null }))
    assert.equal(tab.ended.length, 1)
    assert.equal(env.timers.size, 0)
  }
})
