# OVH Away Access

Last verified: 2 September 2026

## Current position

- Connect with `ssh signal75-vps` from a machine that has the Signal 75 SSH key.
- Codex CLI `0.152.1` is installed for the `debian` user.
- Codex is deliberately signed out. No OpenAI API key or ChatGPT token is stored on OVH yet.
- OVH remains a read-only parallel-test host. The Mac is still the sole live writer.
- The official OVH morning, results and learning timers remain disabled.

## Signing in while away

Use ChatGPT subscription authentication rather than an API key so usage does not unexpectedly move to API billing:

```bash
ssh signal75-vps
codex login --device-auth
```

Complete the device sign-in in a trusted browser, then verify the method:

```bash
codex login status
```

Treat `~/.codex/auth.json` as a password if Codex falls back to file-based credential storage. Never copy it into the repository, a support ticket or a chat.

## Safe maintenance workflow

Do not edit `/srv/signal75/live`, proof files, SQLite databases or generated result files directly.

1. Work in the Git-backed staging checkout at `/srv/signal75/staging-repo`.
2. Ask Codex to inspect status and create a checkpoint before changing anything.
3. Run focused tests and the full test suite.
4. Review the diff.
5. Commit to the staging branch.
6. Promote through the deployment scripts only after Mac-versus-OVH checks pass.

Until formal cutover, any urgent failure can be handled by stopping the OVH test stage and leaving the Mac as primary. At cutover, exactly one host may write picks, settlement, learning and proof.

## Emergency checks

```bash
ssh signal75-vps
cat /srv/signal75/state/health/latest.json
systemctl list-timers --all | grep -E 'signal75|ovh'
systemctl is-active signal75-morning.timer signal75-results.timer signal75-learning.timer
```

Before cutover, the three Signal 75 production timers should report `inactive` and `disabled`; only `ovh-readonly-health.timer` should be enabled.
