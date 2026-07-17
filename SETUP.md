# Setting up zk-age-verifier (go-public checklist)

The peel-out playbook, with the traps we actually hit. Delete this file once you've worked through it.

## 0. First commit

```
git init && git add -A && git commit -m "Initial import"
git branch -M main
git remote add origin git@github.com:pipe23-org/zk-age-verifier.git
git push -u origin main
```

If pushes touch `.github/workflows/*` and your `gh` token lacks `workflow` scope, push over SSH
explicitly (a plain push can fall back to a stale key):
`GIT_SSH_COMMAND="ssh -i ~/.ssh/<key> -o IdentitiesOnly=yes" git push -u origin main`

## 1. Make it public

Branch protection on the free tier requires a **public** repo, and Read the Docs' free tier is
public-only. (PyPI / Trusted Publishing does **not** require public — it keys off the workflow
identity, not visibility.)

## 2. Branch protection (after public)

The API rejects `-f strict=true` (it sends the string `"true"`); send a JSON **boolean** body:

```
gh api -X PUT repos/pipe23-org/zk-age-verifier/branches/main/protection \
  -H "Accept: application/vnd.github+json" --input - <<'JSON'
{ "required_status_checks": { "strict": true,
    "contexts": ["lint","types","docs","demo","test (3.11)","test (3.12)","test (3.13)","test (3.14)"] },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null }
JSON
```

Set the `contexts` to the checks that actually run on PRs — **not** `test-fast` (it only runs on
branch pushes, so requiring it deadlocks merges).

## 3. PyPI Trusted Publisher (no tokens)

Register a **pending** publisher at <https://pypi.org/manage/account/publishing/>:

- Owner: `pipe23-org`  ·  Repository: `zk-age-verifier` (repo name only, not owner/repo)
- Workflow: `release.yml`  ·  Environment: `pypi`

Then create the GitHub environment: `gh api -X PUT repos/pipe23-org/zk-age-verifier/environments/pypi`

## 4. Release

```
# bump pyproject version, THEN regenerate the lock (uv sync --locked fails otherwise):
uv lock
git commit -am "Release 0.1.0" && git push        # via PR if main is protected
git tag -a v0.1.0 -m "0.1.0" && git push origin v0.1.0
```

`release.yml` runs check-version → build → publish → smoke, and an `image` job that pushes
the multi-arch container to `ghcr.io/pipe23-org/zk-age-verifier` (`:X.Y.Z` + `:latest`). A version is
permanent on PyPI once uploaded; re-pushing the same tag only works for *pre-upload* failures
(`skip-existing` covers a partial upload). README/example edits never need a re-release.

## 5. Read the Docs

Import at <https://app.readthedocs.org/> (it auto-detects `.readthedocs.yaml`). If the repo
doesn't appear in the list, use **Import Manually** with the repo URL — that bypasses the stale
discovery list. Add the incoming-webhook URL + secret under the repo's Settings → Webhooks
(events: push, create, delete) so docs rebuild on push and tags become versions.

After the first publish, the PyPI Documentation URL fills in automatically from `[project.urls]`.

## Gotcha: GitHub Action major tags

Some actions publish **no floating `@vX` tag** — `setup-uv` and `cibuildwheel` 404 on `@v8`/`@v3`.
Pin an exact `vX.Y.Z` that resolves and let Dependabot bump it. Verify before committing:
`gh api repos/OWNER/REPO/git/ref/tags/vX`.
