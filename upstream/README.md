# Upstream fix package — desktop runtime plugins fail to load (0.20.4)

Περιεχόμενα:

| File | Τι είναι |
|---|---|
| `ISSUE.md` | Έτοιμο κείμενο για GitHub issue στο `NousResearch/hermes-agent` (αγγλικά, με root cause + evidence + repro). |
| `0001-desktop-sdk-defer-namespace-read.patch` | Το patch για `apps/desktop/src/sdk/runtime.ts` — εφαρμόζεται καθαρά στο `main` (το αρχείο στο main είναι byte-ίδιο με το HEAD μας πριν τη διόρθωση). |

## Το bug σε μία γραμμή

Το production bundle του desktop app δεσμεύει τα SDK namespaces (`__HERMES_PLUGIN_SDK__`,
React, jsx-runtime) στο module scope, σε ένα module που βρίσκεται σε import cycle
(`sdk/index` → `@/contrib/*` → `contrib/runtime-loader` → `sdk/runtime`). Στο bundled build
ο bundler βάζει το `var Db = <sdk namespace>` **μετά** το literal που το διαβάζει, άρα
`Object.keys(undefined)` → `Cannot convert undefined or null to object`.

`loadRuntimePlugin()` περνάει από `sdkImportMap()` για **κάθε** plugin πριν το αξιολογήσει →
σπάει κάθε plugin από δίσκο, ανεξάρτητα από τον κώδικά του. Δεν υπάρχει plugin-side fix.

## Πώς εφαρμόζεται (για maintainer)

```bash
git checkout -b fix/desktop-plugin-sdk-namespace main
git apply 0001-desktop-sdk-defer-namespace-read.patch
git commit -am "fix(desktop): resolve plugin SDK namespaces lazily, not at module scope"
```

## Τοπικό hotfix (αυτό το μηχάνημα)

Στο εγκατεστημένο build έγινε in-place patch στο

```
apps/desktop/release/win-unpacked/resources/app.asar.unpacked/dist/assets/sdk-_WH0yJst.js
apps/desktop/dist/assets/sdk-_WH0yJst.js
```

(αντικατάσταση του `var Lg={…}` με lazy getters· backup: `*.bak-sdkfix`) και η ίδια διόρθωση
μπήκε στον πηγαίο κώδικα. Ένα rebuild της εφαρμογής από αυτόν τον κώδικα βγάζει σωστό bundle,
αλλά **το επόμενο `hermes update` που θα ξαναχτίσει το app θα σβήσει το hotfix** μέχρι να
μπει η διόρθωση upstream.
