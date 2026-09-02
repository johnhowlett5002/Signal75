# Signal 75 OVH Staging Rules

This checkout is the Git-backed OVH maintenance and staging workspace. It is not the active Signal 75 live release.

## Safety boundaries

- Keep the Mac as the only live writer until an explicit, rehearsed cutover is approved.
- Never create `/etc/signal75/live-pipeline-enabled` or `/etc/signal75/production.env` as part of normal maintenance.
- Never enable or start `signal75-morning.timer`, `signal75-results.timer` or `signal75-learning.timer` without explicit cutover approval.
- Do not edit `/srv/signal75/live`, `/srv/signal75/app`, proof files, generated results or SQLite databases in place.
- Do not store Anthropic, OpenAI or Betfair credentials in this repository.
- Do not let shadow or challenger output alter official picks, results, profit or ROI.

## Change workflow

1. Inspect `git status` and create a Git checkpoint before editing.
2. Keep changes focused and preserve existing selection/proof behavior unless the requested task explicitly changes it.
3. Run focused tests, then `python3 -m pytest tests/ -q --tb=short`.
4. Review `git diff --check` and the complete diff before committing.
5. Commit to the staging branch. Deployment remains a separate reviewed operation.

Read `docs/ovh-migration-status.md`, `docs/ovh-away-access.md` and `docs/go-live-intelligence-guardrails.md` before migration, scheduling or scoring work.
