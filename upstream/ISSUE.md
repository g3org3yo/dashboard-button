# [desktop] Every on-disk desktop plugin fails to load in production builds — SDK namespaces are read before they exist

## Summary

In a **production (bundled) build** of the desktop app, *every* plugin loaded from disk
fails to load — `$HERMES_HOME/desktop-plugins/<id>/plugin.js` and the `desktop/plugin.js`
half of a unified package alike. Capabilities → Plugins → *Desktop plugins* shows the row
with status `failed` and the message:

```
Cannot convert undefined or null to object
```

It is not plugin-specific: the exception is thrown **before any plugin code runs**, so no
plugin-side workaround exists.

## Root cause

`apps/desktop/src/sdk/runtime.ts` captures the SDK namespaces in a **module-scope object
literal**:

```ts
const GLOBALS = {
  __HERMES_PLUGIN_SDK__: sdk,
  __HERMES_REACT__: React,
  __HERMES_REACT_JSX__: jsxRuntime,
  __HERMES_REACT_JSX_DEV__: jsxDevRuntime
} as const
```

…and `shimUrl()` / `installPluginSdk()` read from it.

That module sits in an import cycle:

```
sdk/index  →  @/contrib/*  →  contrib/runtime-loader  →  sdk/runtime  →  sdk/index
```

- **Dev (unbundled ESM):** the cycle still yields a live namespace object (`import * as sdk`
  binds the module namespace, whose members resolve lazily), so `Object.keys(sdk)` works.
  This is why the bug is invisible in dev and in vitest.
- **Production (vite/rollup build):** the namespace becomes a hoisted `var`. The bundler is
  free to order the two top-level statements either way, and in the shipped 0.20.4 bundle it
  emits them like this (**byte offsets in one minified chunk**):

  | statement | offset |
  |---|---|
  | `var Lg={__HERMES_PLUGIN_SDK__:Db,__HERMES_REACT__:J,__HERMES_REACT_JSX__:Y,…}` | 158,782 |
  | `var Db=t({…})` — the plugin-SDK namespace itself | 228,399 |

  So `Lg.__HERMES_PLUGIN_SDK__` is `undefined` when the object literal is evaluated
  (`var` — no TDZ error), and the first `Object.keys(GLOBALS[globalKey])` in `shimUrl()`
  throws exactly `TypeError: Cannot convert undefined or null to object`.

## Why it breaks every disk plugin

`loadRuntimePlugin()` calls `installPluginSdk()` and then `unsupportedImports(source)` →
`sdkImportMap()` → `shimUrl()` **for every source**, before evaluating it. The failure is
therefore content-independent.

## Reproduction (production build only)

1. Build the desktop app (production): `apps/desktop` → `vite build` (+ the electron bundle)
   and run the packaged app.
2. Drop any `plugin.js` into `~/.hermes/desktop-plugins/<id>/`.
3. Start the app / hit **Reload desktop plugins**.

Observed (from `~/.hermes/logs/desktop.log`):

```
[renderer console:main] [plugins] runtime load failed (<id>) TypeError: Cannot convert
undefined or null to object (…/win-unpacked/resources/app.asar.unpacked/dist/assets/sdk-<hash>.js:5)
```

…plus a `failed` row in Capabilities → Plugins.

## Fix

Resolve the namespaces at **call time** instead of module scope — `installPluginSdk()` and
the shim builder only ever run once the app is up, so the reads are always safe there and
statement ordering stops mattering.

```ts
function pluginNamespaces() {
  return {
    __HERMES_PLUGIN_SDK__: sdk,
    __HERMES_REACT__: React,
    __HERMES_REACT_JSX__: jsxRuntime,
    __HERMES_REACT_JSX_DEV__: jsxDevRuntime
  }
}

export function installPluginSdk(): void {
  Object.assign(globalThis, pluginNamespaces())
}

function shimUrl(globalKey: keyof ReturnType<typeof pluginNamespaces>): string {
  const names = Object.keys(pluginNamespaces()[globalKey]).filter(…)
  …
}
```

Full patch: `0001-desktop-sdk-defer-namespace-read.patch` (applies cleanly to `main`).

## Testing note (honest)

A vitest unit test **cannot** catch this: in the dev module graph the namespace object is
live, so the existing behaviour passes either way. The regression is bundler-ordering-only.
Two options: (a) rely on the structural fix above (module scope no longer captures the
namespaces, so ordering cannot matter), or (b) add a production-build smoke test that loads
a fixture plugin through `loadRuntimePlugin()` and asserts it registers — which is the
faithful reproducer.

## Impact

Any user who updates to a build containing this ordering loses **every** on-disk desktop
plugin (status `failed`, no workaround on the plugin side). Sibling paths worth checking in
the same audit: any other module-scope capture of a namespace/const from the
`sdk/index` ↔ `contrib` cycle.
