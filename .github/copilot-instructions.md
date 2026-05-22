# GitHub Copilot — repository rules

Multi-agent orchestration platform — eat your own dogfood. Spawn freely.

## Git workflow (REQUIRED)

- Branch per task: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `refactor/<slug>`, `docs/<slug>`.
- Atomic Conventional Commits.
- Push to origin → merge into `main` → delete branch.
- Never commit directly to `main`. Never `--no-verify`. Never force-push to `main`.

## Browser verification (REQUIRED for UI changes)

`tsc` and build only prove the code compiles. Real bugs hide in the browser.

Setup (one-time):

```bash
npm i -D playwright@^1.49
npx playwright install chromium
cp ~/.claude/skills/browser-verify/resources/scan-pages.mjs scripts/scan-pages.mjs
```

Add to `package.json`: `"scan": "node scripts/scan-pages.mjs"`.

Run: `npm run dev` (other shell) → `npm run scan`. Non-zero = real regression.

## Doc editing

Append to existing knowledge files. Never rewrite the rule blocks above.

## More

See `AGENTS.md` and `CLAUDE.md` for fuller context.
