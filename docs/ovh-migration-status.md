# OVH Migration Status

Last verified: 2 September 2026

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
- Current unpromoted candidate: `candidate-shadow-20260901-132823`, combining database snapshot `shadow-input-20260901-094000` with runtime snapshot `runtime-input-20260901-132823`.
- Isolated offline and real-feed shadow workspaces.
- Daily read-only health check at 06:30 UTC.
- Health report: `/srv/signal75/state/health/latest.json`.
- The read-only health timer is installed, enabled and was manually verified healthy with eight checks on 1 September.
- The 2 September health run also passed all eight checks. Both private previews were refreshed through atomic, versioned releases on 2 September and returned HTTP 200.
- Mac-driven real-feed shadow comparison scheduled for 10:40 UK time, with a guarded 11:15 retry if the morning picks were delayed or the first trial was not comparable.
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

1. Allow the scheduled real Betfair feed shadow to run during morning market availability and compare its selections with the Mac.
2. Confirm on the next morning run that the newly transferred rival-memory artifacts remove the Bownder/Divot input mismatch found on 1 September.
3. Repeat parallel comparisons on several racing days; investigate every mismatch before promotion.
4. Define the final writable database ownership/layout for server-owned learning data. Restore capability is now rehearsed; dual writers remain prohibited.
5. Store production credentials in root-readable server environment files only when activation is approved.
6. Perform a rehearsed cutover with the Mac still available as rollback.
7. Configure the public domain, TLS and ports 80/443 only when the server becomes the approved public host.
8. Use the Git-backed staging checkout for any Codex-assisted server edit; never edit the live release or writable data in place. See `docs/ovh-away-access.md`.

## Rollback principle

Until formal cutover, stop any OVH test and continue using the Mac. Do not merge learning writes from both machines. At cutover, exactly one machine may own each writable pipeline stage.
