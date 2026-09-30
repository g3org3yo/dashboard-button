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

## ⚠️ If the plugin shows `failed` instead of loading (Hermes desktop 0.20.x)

Some **Hermes desktop 0.20.x builds** ship a broken plugin-SDK bundle: the app
captures the plugin-SDK namespaces at module scope, *before* the module that
defines them has run, so `Object.keys(undefined)` throws **inside the app's own
plugin loader** — before any plugin code runs. The symptom is therefore
universal (it hits every plugin loaded from disk, not just this one) and looks
like this — Capabilities → Plugins → *Desktop plugins*:

```
dashboard-button    on disk    failed
Cannot convert undefined or null to object
```

…and in `%LOCALAPPDATA%\hermes\logs\desktop.log`:

```
[renderer console:main] [plugins] runtime load failed (<id>) TypeError: Cannot convert
undefined or null to object (.../dist/assets/sdk-<hash>.js:5)
```

**No plugin can work around it** — the throw happens before the plugin is
evaluated. Two ways out:

1. **Update Hermes** once the upstream fix lands: reported in
   [issue #107304](https://github.com/NousResearch/hermes-agent/issues/107304),
   fix proposed in
   [PR #107303](https://github.com/NousResearch/hermes-agent/pull/107303).
2. **Fix the build you already have**, with
   [`tools/hermes-plugin-sdk-hotfix.py`](tools/hermes-plugin-sdk-hotfix.py): it
   finds the app's renderer bundle, rewrites those four SDK globals as lazy
   getters (so they are read when the app is up), syntax-checks the result and
   keeps a backup next to the original file.

```bash
python tools/hermes-plugin-sdk-hotfix.py           # dry run — what would change
python tools/hermes-plugin-sdk-hotfix.py --apply   # patch + verify
# then FULLY restart the Hermes desktop app (close it and reopen it)
```

It is safe to run more than once (an already-fixed bundle is detected and left
alone), it prints every path it touched, and it says which roots it searched —
if your install lives elsewhere, point at it with `--root <dir>`. Afterwards
the *Desktop plugins* row must no longer say `failed`.

`plugin.js` itself needed **no** change for this: the plugin is verified working
on desktop **0.20.4** with the SDK fix applied (sidebar row, in-app page and
statusbar chip all load). The full diagnosis we filed lives in
[`upstream/`](upstream/).

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
tools/               SDK hotfix for the Hermes desktop 0.20.x loader bug
upstream/            diagnosis + patch filed upstream (issue #107304 / PR #107303)
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

`tools/hermes-plugin-sdk-hotfix.py` is a standalone, stdlib-only rescue tool
for the app-side 0.20.x bug described above. `upstream/` holds the diagnosis
and patch as filed upstream (issue #107304 / PR #107303).

## License

MIT — see [LICENSE](LICENSE).
