---
title: "GitHub to Gitee Mirror Sync via GitHub Actions"
date: 2026-06-30
category: docs/solutions/tooling-decisions/
module: development_workflow
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "Need to mirror GitHub repos to Gitee for China-based team access"
  - "Setting up automatic mirror sync between Git hosting platforms"
  - "Colleagues cannot access GitHub due to network restrictions"
tags: [github-actions, gitee, mirror, sync, china-network, git]
---

# GitHub-to-Gitee Mirror Sync via GitHub Actions

## Context

A team member in Shenzhen could not access the `keyapi/fzh-data` GitHub repository because they lacked VPN access. GitHub is intermittently blocked or severely throttled for users in China without a VPN, while Gitee (gitee.com) is a domestic Git hosting platform that remains fully accessible. The repository needed to remain on GitHub as the source of truth, but a read-only mirror on Gitee was required so the Shenzhen colleague could pull code and stay in sync.

The same pattern was replicated for `fzh-web-automation`, confirming it as reusable for any GitHub repo.

## Guidance

A GitHub Actions workflow triggers on every push to `main` and force-pushes the same commit history to a target Gitee repository via HTTPS with a personal access token.

### Step 1: Generate Gitee Token

Gitee → Settings → Private Tokens → Generate new token, scope: **projects**.

### Step 2: Add GitHub Secrets

GitHub repo → Settings → Secrets and variables → Actions → **Repository secrets**:

- `GITEE_USERNAME` — your Gitee username
- `GITEE_TOKEN` — the token from Step 1

Use Repository secrets, not Environment secrets and not Variables.

### Step 3: Create `.github/workflows/sync-to-gitee.yml`

```yaml
name: Sync to Gitee
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Push to Gitee
        run: |
          git remote add gitee https://${{ secrets.GITEE_USERNAME }}:${{ secrets.GITEE_TOKEN }}@gitee.com/keyapi/fzh-data.git
          git push gitee main --force
```

`fetch-depth: 0` ensures full history; `--force` keeps Gitee an exact mirror after rebases.

### Step 4: Create matching Gitee repository

### Step 5: Push to main and verify via GitHub Actions tab

## Why This Matters

- **Avoids VPN dependency** — Shenzhen colleagues clone from Gitee without VPN
- **Zero cost, zero maintenance** — GitHub Actions free tier, no server to maintain
- **Preserves single source of truth** — GitHub remains canonical, Gitee is read-only mirror
- **Reusable** — same pattern, different repo name

### Pitfall Avoided: HTTPS vs SSH in Mirror Actions

Initial attempt used `pixta-dev/repository-mirroring-action@v1` which failed:

```
Unexpected input(s) 'target_repo_username', 'target_repo_token'
fatal: could not read Username for 'https://gitee.com'
```

That action only supports SSH (`ssh_private_key` input), not HTTPS token auth. Direct shell commands avoid this — credentials are embedded in the remote URL, which works with any Git server.

## When to Apply

- GitHub repo needs a read-only mirror on Gitee for China-based colleagues without VPN
- One-way sync (GitHub → Gitee) is sufficient
- You control both GitHub and Gitee repos

Do **not** use for bidirectional sync or when Gitee has independent commits to preserve.

## Examples

### Before: Manual

```bash
git clone git@github.com:keyapi/fzh-data.git
git remote add gitee https://gitee.com/keyapi/fzh-data.git
git push gitee main  # must remember to do this
```

### After: Automated

Shenzhen colleague simply runs:

```bash
git clone https://gitee.com/keyapi/fzh-data.git
git pull  # always up to date, sync delay < 30s
```

### Deployed to two repos

| Repo | Status |
|------|--------|
| `keyapi/fzh-data` | Working (one debug round: switch from third-party action to direct shell) |
| `keyapi/fzh-web-automation` | Working on first attempt (no changes beyond repo name) |

## Related

- Gitee tokens: https://gitee.com/profile/personal_access_tokens
- GitHub Actions secrets: https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions
