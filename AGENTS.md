# Agent rules

## Git workflow (REQUIRED)

- Branch per task. Naming: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `refactor/<slug>`, `docs/<slug>`. One branch = one discrete thing.
- Atomic commits. Conventional Commits format: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.
- Push to origin.
- Merge into `main` (PR if CI gate, otherwise direct fast-forward).
- Delete the branch locally and on origin after merge.

Hard rules:
- Never commit directly to `main`.
- Never `--no-verify` to skip hooks unless explicitly asked.
- Never force-push to `main`.
- Never work in a dirty tree across unrelated tasks — stash or split first.

## Browser verification (REQUIRED for UI changes)

`tsc` and `next build` only prove the code compiles. WebGL contexts, React 19 ref forwarding, hydration drift, pointer-overlap — all compile cleanly and break in the browser.

### Setup (one-time, if not yet installed)

```bash
npm i -D playwright@^1.49
npx playwright install chromium
cp ~/.claude/skills/browser-verify/resources/scan-pages.mjs scripts/scan-pages.mjs
```

Add to `package.json`:

```json
"scripts": { "scan": "node scripts/scan-pages.mjs" }
```

### Run on every UI change

1. `npm run dev` in another shell.
2. `npm run scan`.
3. Exit 0 = clean. Non-zero = real regression. Fix before commit.

Hard rules:
- Don't claim "build passes, ship it" for a UI change.
- Don't commit while scan exits non-zero.

## Subagents

Multi-agent platform — eat your own dogfood. Spawn freely for research-heavy work. Same git + browser-verify rules apply.
