# OVH Migration Status

Last verified: 3 September 2026

## Current ownership

- The Mac is the only live Signal 75 writer.
- The Mac still owns morning picks, settlement, learning, proof, publishing and backups.
- OVH is a read-only parallel-test environment.
- No OVH job writes to the live proof record or the live Mac databases.
- No Anthropic credentials are stored on OVH.

## Working on OVH

- Debian 13, Python 3.13 and the Signal 75 virtual environment.
- Codex CLI `0.152.1` is installed for the `debian` user but deliberately remains signed out. No OpenAI credential is stored on OVH.
- Private dashboard preview on `127.0.0.1:8750`, reached through the SSH tunnel.
- Private public-site preview on `127.0.0.1:8751`, reached through a separate SSH tunnel. This does not serve the live domain.
- Verified read-only snapshots of all three SQLite databases.
- Immutable, hash-verified snapshots of the four large rival-memory runtime artifacts. Shadow workspaces link to these snapshots instead of duplicating about 526 MB on every run.
- Current unpromoted candidate: `candidate-shadow-20260903-080356`, combining database snapshot `shadow-input-20260903-080356` with runtime snapshot `runtime-input-20260903-080356`.
- Isolated offline and real-feed shadow workspaces.
- Daily read-only health check at 06:30 UTC.
- Health report: `/srv/signal75/state/health/latest.json`.
- The read-only health timer is installed, enabled and was manually verified healthy with eight checks on 1 September.
- The 2 September health run also passed all eight checks. Both private previews were refreshed through atomic, versioned releases on 2 September and returned HTTP 200.
- Mac-driven database/runtime shadow candidate preparation is scheduled for 08:30 UK time.
- Real-feed shadow comparisons are scheduled for 10:10 UK time, with a guarded 10:25 retry if the morning picks are delayed. The comparison reuses the dated, verified candidate so the multi-gigabyte transfer is no longer inside the 20-minute comparison window.
- The 3 September scheduled comparison completed at 10:11 and was valid: both outputs were dated 3 September, the generation gap was under 10 minutes, OVH completed normally and all proof files remained unchanged. Two of three selections matched. The differing third selection was explained by independent live-feed snapshots: the Mac saw 39 markets and 330 runners at about 10:00, while OVH saw 40 markets and 342 runners at about 10:10. The later feed contained `MODERN TIMES`, which was absent from the Mac race comparison. This is recorded as a comparable `different` result, not a code or database failure.
- Official selection policy `2026-09-02-context-guard-v1` is installed in OVH staging. Its configuration validator, behavioural canary and fail-closed test gate pass on Debian 13. The future OVH morning service already delegates to the same canonical `run_morning_pipeline.py`, so these checks become mandatory when OVH is promoted to primary.
- The shadow schedule refuses stale Mac picks and never publishes its test output.
- Deployment-state manifests compare Mac and OVH code, proof artifacts and database summaries.
- Shadow workspaces now include the four non-SQLite rival-memory artifacts used by the live generator: the H2H master, H2H profiles, historic-rival profiles and field-relationship profiles.
- A shadow comparison is only considered comparable when the Mac and OVH outputs were generated within 20 minutes of each other. Late same-day reruns are explicitly rejected as timing-invalid comparisons.
- An isolated restore rehearsal passed on 1 September for all three databases. It verified source hashes, copied each database to disposable storage, checked SQLite integrity and table counts, proved the restored copy was writable, rechecked integrity, confirmed the immutable sources were unchanged and removed the temporary copies.
- Restore audit report: `/srv/signal75/state/restore-tests/restore-rehearsal-20260901-133256.json`.
- Candidate, database-snapshot, runtime-snapshot and shadow-run retention is guarded by strict timestamped-name patterns and has a dry-run mode.
- Morning, evening-results and nightly-learning systemd definitions are installed but disabled and inactive. They use `Europe/London` schedules matching the Mac timetable.
- Every future live stage requires an exact activation marker and `SIGNAL75_OVH_ROLE=primary`; neither activation file exists on OVH.
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

## Deliberately not active

- No enabled or active OVH morning-picks timer.
- No enabled or active OVH settlement or nightly-learning timer.
- No OVH public publishing.
- No promoted writable OVH database.
- No public dashboard exposure.

## Remaining gates before cutover

1. Repeat parallel comparisons on several racing days; distinguish expected live-price/market timing differences from code, configuration or data mismatches before promotion.
2. Confirm that matching runners receive equivalent contextual, rival-memory and policy treatment on subsequent comparisons. The 3 September matched runners used the same policy and context evidence, with score movement explained by independently fetched live prices.
3. Keep recording market count, runner count and generation time in every comparison so feed-timing differences remain auditable.
4. Define the final writable database ownership/layout for server-owned learning data. Restore capability is now rehearsed; dual writers remain prohibited.
5. Store production credentials in root-readable server environment files only when activation is approved.
6. Perform a rehearsed cutover with the Mac still available as rollback.
7. Configure the public domain, TLS and ports 80/443 only when the server becomes the approved public host.
8. Use the Git-backed staging checkout for any Codex-assisted server edit; never edit the live release or writable data in place. See `docs/ovh-away-access.md`.

## Rollback principle

Until formal cutover, stop any OVH test and continue using the Mac. Do not merge learning writes from both machines. At cutover, exactly one machine may own each writable pipeline stage.
