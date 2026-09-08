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

- Hermes **desktop** app (plugins load only there).
- The dashboard server, which is *not* started by this plugin. Either:
  - run `hermes dashboard` when you want it, or
  - pair the plugin with an auto-start watchdog so it is always available.

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
   `g3org3yo/dashboard-button`.
2. Pick **Desktop UI** in the dialog and confirm.
3. The plugin appears in the sidebar and statusbar immediately.

To replace an existing install: `hermes://plugin/install?repo=g3org3yo/dashboard-button&force=1`.

## Development

The plugin is a single plain-ESM file ([`plugin.js`](plugin.js)) using the
`@hermes/plugin-sdk`. Drop the folder into your local
`<hermes-home>/desktop-plugins/` and it hot-reloads on save — no build step.

## License

MIT — see [LICENSE](LICENSE).
