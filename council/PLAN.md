# Current Plan (Drafter)

What is open and what comes next - nothing else.  **What was built and why is in
[DECISIONS.md](DECISIONS.md)** (D1-D56); ideas that are not planned are in
[ideas/README.md](ideas/README.md).  Until 2026-10-25 this file also listed every finished
milestone; that was a second copy of the decision log, and the stale boxes in it (a "batch ping"
that no longer exists, checks done weeks ago) are how settled topics came back up.

## Field test of 2.1.0 (D50)
- [ ] `Ctrl-A` + ping over the whole inventory on the server (the confirmation above 200)
- [ ] `Ctrl-E` after a sweep: open the CSV in Excel - umlauts, columns, delimiter
- [ ] The first start after the update deletes nothing younger than 180 days (`log_keep_days`)
- [ ] The two newcomers: is the search section's "four you need" enough to start with?

## Field test of 2.2.0 (D51)
- [ ] Lab work: several lines of one terminal server (`3 7 12`) in tmux - all logged in?
- [ ] A switch + a terminal-server line marked together: one session, ssh and console pane
- [ ] `local` in console panes on the real switches; `Ctrl-K` warning read once by the newcomers

## Field test of 2.3.0 (D52-D54)
- [ ] Ruffy: `ssh_command = ct ssh` - the password is typed in (if not: `truffle --debug`, then the debug log)
- [ ] A lab terminal server with `Terminal server <local>`: its account, then the switch login behind it

## Field test of 2.4.0 / 2.5.0 (D55, D56)
- [ ] A device that is not in the list: type its IP, Enter, then `Ctrl-N` to save it
- [ ] A lab box without RADIUS saved with `Login <local>`: the console's local account gets you in
- [ ] `admin@<ip>` (manual): ssh's own prompt, you type the password; `manual_user` pre-fills the User line
- [ ] Devices saved with 2.4.0 still there after the update (`admin@` ones are now manual)

## Now: field test of 2.6.0 (D57)
- [ ] The age of the device list on the server: the top bar note, and `truffle --check` exit 1 from cron
- [ ] A new export + `Ctrl-R` clears the note - and is 30 days (`data_max_age_days`) the right number for
      how often the export really runs?
- [ ] More than 9 marked: the ones left out stay marked, the next Enter opens them
- [ ] TRuffle started inside tmux: `Ctrl-b L` comes back, and logging out of the last pane does too
- [ ] A terminal server that does not answer: `Ctrl-Q` while connecting leaves no `ok` in the SSH column
- [ ] Ruffy: a device name with a `#` in it - the pane border shows the name, not `%0`
- [ ] D59: the texts - anything left that says "switch" where it is not one (Ruffy and the newcomers)
- [ ] D59: the local-account window on the MacBook - the whole sentence, and the password line read once
      by someone who has not seen it before
- [ ] Ruffy (D58): `Ctrl-C` on a switch that does not answer, through `ct ssh` - the SSH column says
      `failed`, not `ok`; and a normal login through `ct ssh` is still `ok` afterwards

## Still to confirm on RHEL
- [ ] `truffle --check` prints `ssh results : ok` (the session detection of D45 / D46)
- [ ] A `#(...)` in a device name on RHEL's tmux: pane title and log header show it literally, nothing
      runs (D44 #3, D57 #4 - only tmux 3.8 was tried)

## Next
Nothing planned.  Open from D57: the rest of "running inside tmux as a supported case" (`Ctrl-T` from
inside tmux, the top bar saying you are in it).  The login matrix stays frozen until the 2.4.0 / 2.5.0
boxes above are ticked.  Candidates from the feature review ([REVIEW-features.md](REVIEW-features.md)),
none decided: "down since" next to the age (M7), copy an IP to the clipboard (M8).

## Delivery
- Server: the internal git, updated with the bundle (`tools/make-bundle.py`) for big changes.
- Bump `VERSION` in `src/truffle/__init__.py` before building a bundle whose contents changed.
