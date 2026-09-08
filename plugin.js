/**
 * Hermes desktop plugin: "Dashboard button".
 *
 * One-click access to the Hermes Web Dashboard (127.0.0.1:9119) from the
 * Hermes desktop app:
 *   - Sidebar row "Dashboard": opens the dashboard as its own view in the
 *     main pane (route /dashboard).
 *   - The /dashboard page: if the dashboard server is down it shows the
 *     state and loads BY ITSELF as soon as the server is ready (no second
 *     click, no manual refresh). If the connection drops while the page is
 *     open, it reloads automatically when the server returns.
 *   - Statusbar chip with a live status dot: opens the dashboard in your
 *     default browser — if it is down, it waits for it to come up and opens
 *     automatically.
 *
 * Pure front-end plugin: it does NOT call the agent and does NOT spend any
 * tokens. It only *waits* for the dashboard server — start it with
 * `hermes dashboard`, or pair this with an auto-start watchdog (see the
 * companion script in `companion/dashboard_watchdog.py`).
 *
 * Plain ESM, loaded uncompiled — UI is jsx() calls, not JSX syntax.
 * Only these imports resolve: @hermes/plugin-sdk, react, react/jsx-runtime.
 */
import { cn, haptic, host, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useRef, useState } from 'react'

const ID = 'dashboard-button'
const DASH_URL = 'http://127.0.0.1:9119/'
const POLL_MS = 4000 // how often we probe liveness while the page is open
const START_WAIT_TRIES = 50 // max 50 × 3s ≈ 2.5 min of waiting for startup

// ctx.os is only available inside register(); stash it for click handlers.
let os = null

async function isDashboardUp(timeoutMs = 2500) {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    await fetch(DASH_URL, { method: 'GET', mode: 'no-cors', signal: ctrl.signal })
    return true
  } catch {
    return false
  } finally {
    clearTimeout(t)
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Makes sure the dashboard is up, then calls open().
 * When it is down, tells the user and polls until it comes up (the server /
 * an auto-start watchdog is expected to start it) or until it times out.
 */
async function ensureUpThen(open) {
  haptic('tap')
  if (await isDashboardUp()) {
    return open()
  }
  host.notify({
    kind: 'info',
    message:
      'Dashboard is starting — it will open automatically once ready (usually within a minute).'
  })
  for (let i = 0; i < START_WAIT_TRIES; i++) {
    await sleep(3000)
    if (await isDashboardUp()) {
      return open()
    }
  }
  host.notify({
    kind: 'error',
    message:
      "The dashboard did not start. Make sure `hermes dashboard` is running (or that your auto-start watchdog is active), then try again."
  })
}

async function openInBrowser() {
  await ensureUpThen(async () => {
    if (!os) {
      host.notify({ kind: 'error', message: 'The OS bridge is not available.' })
      return
    }
    const opened = await os.openExternal(DASH_URL)
    if (opened === false) {
      host.notify({ kind: 'error', message: 'Could not open the browser.' })
    }
  })
}

/** Dashboard liveness: 'checking' | 'up' | 'down' */
function useDashboardState(pollMs) {
  const [state, setState] = useState('checking')
  useEffect(() => {
    let alive = true
    let timer = null
    const tick = async () => {
      const up = await isDashboardUp()
      if (!alive) return
      setState(up ? 'up' : 'down')
      timer = setTimeout(tick, pollMs)
    }
    tick()
    return () => {
      alive = false
      if (timer) clearTimeout(timer)
    }
  }, [pollMs])
  return state
}

function DashboardChip() {
  const state = useDashboardState(15000)
  const dot =
    state === 'up'
      ? 'bg-(--ui-success)'
      : state === 'down'
        ? 'bg-(--ui-danger,#f87171)'
        : 'bg-(--ui-text-quaternary)'
  const label = state === 'up' ? 'Dashboard' : state === 'down' ? 'Dashboard ↓' : 'Dashboard …'
  return jsx(
    'button',
    {
      type: 'button',
      title: 'Open the Hermes Web Dashboard in your browser',
      className: cn(
        'inline-flex h-full items-center gap-1.5 px-1.5 text-[0.6875rem] transition-colors',
        'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
      ),
      onClick: openInBrowser,
      children: [
        jsx('span', { className: cn('inline-block h-1.5 w-1.5 rounded-full', dot) }),
        'Dashboard'
      ]
    }
  )
}

function DashboardPage() {
  const frameRef = useRef(null)
  const [size, setSize] = useState(null)
  const state = useDashboardState(POLL_MS)
  const [frameKey, setFrameKey] = useState(0) // bumped to force an iframe reload

  useEffect(() => {
    const el = frameRef.current
    if (!el) return
    const report = () => setSize(`${el.clientWidth}x${el.clientHeight}`)
    report()
    const ro = new ResizeObserver(report)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Whenever the dashboard becomes 'up' again, reload the iframe fresh.
  const prevUp = useRef(null)
  useEffect(() => {
    if (prevUp.current === false && state === 'up') {
      setFrameKey((k) => k + 1)
    }
    prevUp.current = state === 'up'
  }, [state])

  const statusBadge =
    state === 'up' ? 'Online' : state === 'down' ? 'Offline' : 'Checking…'

  const body =
    state === 'up'
      ? jsx('iframe', {
          key: frameKey,
          ref: frameRef,
          src: DASH_URL,
          title: 'Hermes Dashboard',
          className: 'w-full border-0',
          style: { display: 'block', flex: '1 1 auto', minHeight: 500 }
        })
      : jsx(
          'div',
          {
            className:
              'flex min-h-0 flex-1 flex-col items-center justify-center gap-3 px-6 text-center'
          },
          jsx('div', {
            className: 'text-sm font-medium text-(--ui-text-secondary)',
            children:
              state === 'down'
                ? 'The dashboard is not running'
                : 'Checking dashboard status…'
          }),
          jsx('div', {
            className: 'max-w-md text-xs leading-relaxed text-(--ui-text-tertiary)',
            children:
              'This page will load by itself as soon as the dashboard server is ready (start it with `hermes dashboard`, or let your auto-start watchdog do it). If it stays down for more than a minute or two, check that the server is running.'
          }),
          jsx('button', {
            type: 'button',
            className:
              'rounded border border-(--ui-stroke-secondary) px-3 py-1.5 text-xs text-(--ui-text-secondary) transition-colors hover:bg-(--chrome-action-hover) hover:text-foreground',
            onClick: openInBrowser,
            children: 'Open in browser when ready'
          })
        )

  return jsxs('div', {
    className: 'flex h-full w-full min-h-0 flex-col',
    children: [
      jsxs('div', {
        className:
          'flex shrink-0 items-center justify-between gap-2 border-b border-(--ui-stroke-secondary) px-3 py-1.5 text-xs',
        children: [
          jsxs('span', {
            className: 'flex items-center gap-2 font-medium text-(--ui-text-secondary)',
            children: [
              'Hermes Dashboard',
              jsx('span', {
                'data-testid': 'dbg-status',
                className: 'rounded bg-(--chrome-action-hover) px-1.5 py-0.5 font-normal',
                children: statusBadge
              }),
              size
                ? jsx('span', { className: 'font-normal text-(--ui-text-tertiary)', children: `· ${size}` })
                : null
            ]
          }),
          jsx('button', {
            type: 'button',
            className:
              'rounded px-2 py-1 text-(--ui-text-tertiary) transition-colors hover:bg-(--chrome-action-hover) hover:text-foreground',
            onClick: openInBrowser,
            children: 'Open in browser ↗'
          })
        ]
      }),
      body
    ]
  })
}

export default {
  id: ID, // must match the folder name
  name: 'Dashboard Button',
  register(ctx) {
    os = ctx.os

    // In-app page mounted in the workspace pane, reachable from the sidebar.
    ctx.register({
      id: 'route',
      area: ROUTES_AREA,
      data: { path: '/dashboard' },
      render: () => jsx(DashboardPage, {})
    })

    // Sidebar navigation row (the one-click door to the dashboard view).
    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      data: { path: '/dashboard', label: 'Dashboard', codicon: 'globe' }
    })

    // Statusbar chip -> default browser (waits for startup when needed).
    ctx.register({
      id: 'chip',
      area: 'statusBar.right',
      order: 200,
      render: () => jsx(DashboardChip, {})
    })
  }
}
