# OVH Migration Status

Last verified: 5 September 2026, 13:35 Europe/London

## Current ownership

- OVH is the primary Signal 75 pipeline host.
- The verified live release is `/srv/signal75/prelive/releases/prelive-20260905-123200`, exposed through `/srv/signal75/live`.
- OVH owns settlement, learning, proof and GitHub publication from the 5 September evening cycle onward.
- The OVH morning timer will arm at 00:05 on 6 September and first run at 10:00 Europe/London.
- The Mac production writer jobs are persistently disabled and remain available only for rollback.
- The public static site remains on GitHub Pages; OVH runs the pipeline and publishes its verified outputs to GitHub.
- No Anthropic credentials are stored on OVH and Anthropic features remain disabled.

## Working on OVH

- Debian 13, Python 3.13 and the Signal 75 virtual environment.
- Codex CLI `0.152.1` is installed for the `debian` user but deliberately remains signed out. No OpenAI credential is stored on OVH.
- Private dashboard preview on `127.0.0.1:8750`, reached through the SSH tunnel.
- Private public-site preview on `127.0.0.1:8751`, reached through a separate SSH tunnel. This does not serve the live domain.
- Verified read-only snapshots of all three SQLite databases.
- Immutable, hash-verified snapshots of the four large rival-memory runtime artifacts. Shadow workspaces link to these snapshots instead of duplicating about 526 MB on every run.
- Promoted candidate: `candidate-shadow-20260905-122350`, combining database snapshot `shadow-input-20260905-122350` with runtime snapshot `runtime-input-20260905-122350`.
- Isolated offline and real-feed shadow workspaces.
- Daily read-only health check at 06:30 UTC.
- Health report: `/srv/signal75/state/health/latest.json`.
- The read-only health timer is installed, enabled and was manually verified healthy with eight checks on 1 September.
- The 2 September health run also passed all eight checks. Both private previews were refreshed through atomic, versioned releases on 2 September and returned HTTP 200.
- Mac-driven database/runtime shadow candidate preparation is scheduled for 08:30 UK time.
- Shadow comparisons are scheduled for 10:10 UK time, with a guarded 10:25 retry if the morning picks are delayed. Each run records both an independent OVH live-feed comparison and a deterministic replay of the Mac's captured feed. The shadow workspace now includes the Mac's dated consensus overlay, script-tipster overlay and tipster-intelligence evidence so the deterministic comparison holds every selection input constant. The comparison reuses the dated, verified candidate so the multi-gigabyte transfer is no longer inside the 20-minute comparison window.
- The 3 September scheduled comparison completed at 10:11 and was valid: both outputs were dated 3 September, the generation gap was under 10 minutes, OVH completed normally and all proof files remained unchanged. Two of three selections matched. The differing third selection was explained by independent live-feed snapshots: the Mac saw 39 markets and 330 runners at about 10:00, while OVH saw 40 markets and 342 runners at about 10:10. The later feed contained `MODERN TIMES`, which was absent from the Mac race comparison. This is recorded as a comparable `different` result, not a code or database failure.
- Official selection policy `2026-09-02-context-guard-v1` is installed in OVH staging. Its configuration validator, behavioural canary and fail-closed test gate pass on Debian 13. The future OVH morning service already delegates to the same canonical `run_morning_pipeline.py`, so these checks become mandatory when OVH is promoted to primary.
- The shadow schedule refuses stale Mac picks and never publishes its test output.
- Deployment-state manifests compare Mac and OVH code, proof artifacts and database summaries.
- Shadow workspaces now include the four non-SQLite rival-memory artifacts used by the live generator: the H2H master, H2H profiles, historic-rival profiles and field-relationship profiles.
- A shadow comparison is only considered comparable when the Mac and OVH outputs were generated within 20 minutes of each other. Late same-day reruns are explicitly rejected as timing-invalid comparisons.
- An isolated restore rehearsal passed on 1 September for all three databases. It verified source hashes, copied each database to disposable storage, checked SQLite integrity and table counts, proved the restored copy was writable, rechecked integrity, confirmed the immutable sources were unchanged and removed the temporary copies.
- Restore audit report: `/srv/signal75/state/restore-tests/restore-rehearsal-20260901-133256.json`.
- A complete writable release was staged and promoted on 5 September at `/srv/signal75/prelive/releases/prelive-20260905-123200`.
- The pre-live release uses independent copies of all three SQLite databases and all four large rival-memory files. Every database passed `PRAGMA quick_check` and a transactional write probe.
- Pre-live readiness report: `/srv/signal75/prelive/state/readiness-latest.json`; current status is `ready_for_controlled_cutover` with no failures.
- An atomic pre-live release switch and rollback rehearsal passed on 4 September and restored `prelive-20260904-134948`. Report: `/srv/signal75/prelive/state/rollback-rehearsal-latest.json`.
- The 4 September 10:10 comparison was valid but different: two of three official selections matched. A later near-simultaneous retry also differed because independent Betfair snapshots changed prices and rankings.
- A deterministic 4 September replay then supplied Mac and OVH with the same captured Betfair feed, consensus overlay and candidate learning inputs. Both selected `HARRYS HOPE`, `HANDLETHEKETTLE` and `ASHDOWN FOREST` in the same order, at the same displayed prices and scores. The comparison report is `data/deployment_state/real_feed_trials/mac-vs-ovh-frozen-2026-09-04.json`.
- Frozen-feed replay is restricted to `SIGNAL75_TEST_MODE=1` and now skips the tipster-memory writer, so it cannot be mistaken for a production run or write replay evidence into SQLite learning.
- The deterministic result proves engine parity, but the afternoon candidate is no longer current: the Mac's settlement and learning jobs updated the live databases later that evening. Full evidence payloads therefore differ from the older candidate. OVH remains unactivated until a fresh, quiescent snapshot is staged and passes the same deterministic gate.
- Active pipeline scripts now resolve the repository from their own file location and invoke child scripts with the current virtual-environment Python. A regression test prevents Mac-home paths or `/usr/bin/python3` from returning to those entrypoints.
- Candidate, database-snapshot, runtime-snapshot and shadow-run retention is guarded by strict timestamped-name patterns and has a dry-run mode.
- Evening-results and nightly-learning timers are enabled and active. The daily morning timer is temporarily disabled; the persistent `signal75-arm-morning.timer` will enable and start it at 00:05 on 6 September. This avoids replaying the already-completed 5 September morning run and still survives a VPS reboot before midnight.
- Every live stage requires the exact activation marker and `SIGNAL75_OVH_ROLE=primary`; both gates are active.
- The root-only OVH production environment is installed at `/etc/signal75/production.env`, validates successfully and contains no Anthropic credential. The separate activation marker remains absent, so its presence cannot start a production job.
- A clean publishing checkout is prepared at `/srv/signal75/git/Signal75`. Live releases can use it through `SIGNAL75_PUBLISH_GIT_REPO` without embedding Git metadata in the writable pipeline release.
- OVH has a dedicated GitHub deploy key with repository write permission. Read/fetch and non-mutating push permission checks passed under the `debian` service account.
- All future live stages share `/run/lock/signal75-live-pipeline.lock`. An overlap rehearsal confirmed a second process is refused, and a failure-handler rehearsal wrote an isolated state report.

## Security state

- SSH key login is required.
- Password login and root login are disabled.
- SSH is restricted to the `debian` account.
- UFW is active with default-deny incoming traffic.
- Only port 22 is publicly allowed during private testing.
- The stock nginx public site is disabled. Both Signal 75 previews listen on loopback only.
- Ports 80 and 443 stay closed until the public-site cutover and TLS setup.
- Automatic Debian security updates are enabled.

## Deliberately not public

- The private intelligence dashboard remains loopback-only on OVH and requires the SSH tunnel.
- Ports 80 and 443 remain closed because the public static site is still served by GitHub Pages.
- OVH Codex remains signed out and no OpenAI or Anthropic API credential is stored on the VPS.

## Post-cutover verification

1. Confirm the 5 September 19:00 results service completes and publishes normally.
2. Confirm the 5 September 23:10 learning service completes and all three SQLite databases remain healthy.
3. Confirm the morning timer becomes active at 00:05 and the 6 September 10:00 morning pipeline publishes normally.
4. Keep the Mac rollback files and OVH backups until those three real cycles have passed.
5. Add server-side equivalents for non-critical Mac-only conveniences such as early-result polling and late-market shadow publishing only after the core live cycle is stable.

## Rollback principle

If a live OVH stage fails, stop and disable the three OVH production timers and remove the activation marker before re-enabling any Mac writer. Never allow both hosts to write. Point `/srv/signal75/live` back to the previous verified release only while OVH writers are stopped. Preserve the failed release and logs for diagnosis rather than merging its SQLite writes into the Mac copy.
