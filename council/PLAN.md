# Current Plan (Drafter)

What is open and what comes next - nothing else.  **What was built and why is in
[DECISIONS.md](DECISIONS.md)** (D1-D54); ideas that are not planned are in
[ideas/README.md](ideas/README.md).  Until 2026-10-25 this file also listed every finished
milestone; that was a second copy of the decision log, and the stale boxes in it (a "batch ping"
that no longer exists, checks done weeks ago) are how settled topics came back up.

## Field test of 2.1.0 (D50)
- [ ] `Ctrl-A` + ping over the whole inventory on the server (the confirmation above 200)
- [ ] `Ctrl-E` after a sweep: open the CSV in Excel - umlauts, columns, delimiter
- [ ] The first start after the update deletes nothing younger than 180 days (`log_keep_days`)
- [ ] The two newcomers: is the search section's "four you need" enough to start with?

## Now: field test of 2.2.0 (D51)
- [ ] Lab work: several lines of one terminal server (`3 7 12`) in tmux - all logged in?
- [ ] A switch + a terminal-server line marked together: one session, ssh and console pane
- [ ] `local` in console panes on the real switches; `Ctrl-K` warning read once by the newcomers

## Field test of 2.3.0 (D52-D54)
- [ ] Ruffy: `ssh_command = ct ssh` - the password is typed in (if not: `truffle --debug`, then the debug log)
- [ ] A lab terminal server with `Terminal server <local>`: its account, then the switch login behind it

## Still to confirm on RHEL
- [ ] `truffle --check` prints `ssh results : ok` (the session detection of D45 / D46)

## Next
Nothing planned.  Candidates from the feature review ([REVIEW-features.md](REVIEW-features.md)),
none decided: "down since" next to the age (M7), copy an IP to the clipboard (M8).

## Delivery
- Server: the internal git, updated with the bundle (`tools/make-bundle.py`) for big changes.
- Bump `VERSION` in `src/truffle/__init__.py` before building a bundle whose contents changed.
