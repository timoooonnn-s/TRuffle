# Current Plan (Drafter)

What is open and what comes next - nothing else.  **What was built and why is in
[DECISIONS.md](DECISIONS.md)** (D1-D50); ideas that are not planned are in
[ideas/README.md](ideas/README.md).  Until 2026-10-25 this file also listed every finished
milestone; that was a second copy of the decision log, and the stale boxes in it (a "batch ping"
that no longer exists, checks done weeks ago) are how settled topics came back up.

## Now: field test of 2.1.0 (D50)
- [ ] `Ctrl-A` + ping over the whole inventory on the server (the confirmation above 200)
- [ ] `Ctrl-E` after a sweep: open the CSV in Excel - umlauts, columns, delimiter
- [ ] The first start after the update deletes nothing younger than 180 days (`log_keep_days`)
- [ ] The two newcomers: is the search section's "four you need" enough to start with?

## Still to confirm on RHEL
- [ ] `truffle --check` prints `ssh results : ok` (the session detection of D45 / D46)

## Next
Nothing planned.  Candidates from the feature review ([REVIEW-features.md](REVIEW-features.md)),
none decided: "down since" next to the age (M7), copy an IP to the clipboard (M8).

## Delivery
- Server: the internal git, updated with the bundle (`tools/make-bundle.py`) for big changes.
- Bump `VERSION` in `src/truffle/__init__.py` before building a bundle whose contents changed.
