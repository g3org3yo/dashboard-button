# Dashboard Button — Hermes desktop plugin

One-click access to the **Hermes Web Dashboard** (`http://127.0.0.1:9119`)
from the Hermes desktop app.

**[Install in Hermes](hermes://plugin/install?repo=g3org3yo/dashboard-button)** — or paste the link below into a chat / browser address bar on the machine running Hermes Desktop:

```
hermes://plugin/install?repo=g3org3yo/dashboard-button
```

## What it gives you

- **Sidebar row "Dashboard"** — opens the dashboard as its own view in the
  main pane (in-app, no browser tab).
- **Auto-loading page** — if the dashboard server is down, the page shows the
  status and **loads by itself** the moment the server is ready. If the
  connection drops while the page is open, it reloads automatically when the
  server returns. No second click, no manual refresh.
- **Statusbar chip with a live dot** — green: online · red: offline ·
  grey: checking. Click opens the dashboard in your default browser; when the
  server is down it waits for it to come up and opens automatically (up to
  ~2.5 minutes, then it tells you).

Pure front-end: **no agent involved, no tokens spent.** The plugin only
*waits* for the dashboard server — it never starts it itself.

## Requirements

- Hermes **desktop** `>= 0.21.2` (earlier 0.20.x builds fail to load *any*
  on-disk desktop plugin; see the note below).
- The dashboard server, which is *not* started by this plugin. Either:
  - run `hermes dashboard` when you want it, or
  - pair the plugin with an auto-start watchdog so it is always available.

### Why 0.21.2 and not 0.20.x

On 0.20.x the app captured the plugin-SDK namespaces at module scope, before the
module defining them had run, so the app's **own** plugin loader threw
`Cannot convert undefined or null to object` and every desktop plugin showed
`failed` — before any plugin code ran. That is fixed upstream (commit
`6c3d4a4af70`, *resolve plugin SDK namespaces lazily*), first shipped in
**0.21.2**, so this plugin simply requires that version instead of shipping a
workaround. On 0.21.2+ it loads as-is; the sidebar row, in-app page and
statusbar chip all work.

## Auto-start watchdog (optional, Windows)

The repo ships a hardened watchdog script —
[`companion/dashboard_watchdog.py`](companion/dashboard_watchdog.py) — the one
this plugin was built alongside. It starts `hermes dashboard` whenever the
port is down and stays silent when everything is fine. Wire it as a **no-agent
cron job** that runs every minute:

- Windows path: `%LOCALAPPDATA%\hermes\scripts\dashboard_watchdog.py`
  (adjust `HOME`/`LOCK`/`LOGDIR` at the top of the file for other layouts).
- The script is safe under concurrent execution: an atomic `O_EXCL` lockfile
  guarantees only one dashboard is ever booted, even if two scheduler ticks
  fire at the same time (a real failure mode on Windows after updates, where
  a dashboard start rebuilds the web UI and takes ~a minute).

## Install

1. Click the badge/link above (opens Hermes Desktop with a confirmation
   dialog), or in the app: **Settings → Plugins → Install from Git** and paste
   `g3org3yo/dashboard-button` — or from a terminal:

   ```bash
   hermes plugins install g3org3yo/dashboard-button --enable
   ```
2. **Turn the desktop half on**: **Settings → Plugins → Desktop plugins** → enable
   *dashboard-button*. Desktop parts are opt-in by design, so the plugin stays
   inert until you flip it on.
3. The sidebar row and the statusbar chip appear immediately.

To replace an existing install: `hermes://plugin/install?repo=g3org3yo/dashboard-button&force=1`.

## Layout

```
plugin.yaml          manifest (name, version, requires_hermes, tags)
__init__.py          agent half — intentionally empty, registers nothing
desktop/plugin.js    the actual plugin: sidebar row + in-app page + statusbar chip
companion/           optional Windows auto-start watchdog for `hermes dashboard`
```

The repo is a **single package for both SDKs**: `plugin.yaml` + `__init__.py`
make it a valid, installable Hermes plugin, and everything under `desktop/` is
the half the app loads inside its renderer. `hermes plugins validate .` runs the
same gates the catalog uses (manifest, capability probe, security scan, desktop
surface) and passes.

## Development

The desktop half is a single plain-ESM file ([`desktop/plugin.js`](desktop/plugin.js))
using the `@hermes/plugin-sdk`. Drop the folder into your local
`<hermes-home>/desktop-plugins/` and it hot-reloads on save — no build step.

The repo ships **no workarounds for the app itself**: the 0.20.x plugin-loader
bug is fixed upstream and handled by `requires_hermes` instead (see
[Requirements](#requirements)).

## License

MIT — see [LICENSE](LICENSE).
