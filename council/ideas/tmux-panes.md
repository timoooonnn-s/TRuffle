# Several switches at once in tmux panes

**Status: BUILT on the `tmux-version` branch (2026-10-03), experimental, not merged.**
The user wanted to try it before deciding. Option 1 (one login via a handover) was chosen and implemented,
including every piece of hardening listed below. Tests: `tests/test_handover.py`.

What changed against the plan while building it:
- **Results do not travel through the socket.** Each pane writes its own outcome into the shared status
  file (`UserState.save_status`, which already merges by time). That removed the DONE protocol, and it means
  results survive however long a session runs, instead of being lost when the user detaches. The socket is
  therefore closed as soon as the panes have fetched their login - exactly the "only open while panes start"
  promise, which the original design could not keep.
- **Panes inherit the tmux *server's* environment, not TRuffle's.** HOME and the XDG variables are passed
  explicitly on the pane command line, otherwise a tmux server started earlier writes favourites and results
  somewhere else. This cost an hour to find and is the kind of thing only a real run surfaces.
- **`Ctrl-T` reattaches** from TRuffle. The original plan had no way back *in*; the user asked for it
  immediately, which confirmed the gap.
- The tmux status bar and pane borders carry the key hints, so the way back is visible without the README.
- Pane titles must be set by the parent against a pane id; a pane setting its own title renames whichever
  pane happens to be active.

## How it would be used
1. Open TRuffle normally, **outside** tmux.
2. **One** switch: Enter connects as today, inside TRuffle. Nothing changes.
3. **Two or more:** mark them with **Tab** (fzf-style; `Shift-Tab` unmarks moving up). With the mouse, right-click a row or
   click its left edge. Marked rows get a `+`, and the top bar shows "3 marked".
4. Choose **ssh** and press Enter. TRuffle starts its own tmux session (`truffle-HHMMSS`) with **one pane per switch**
   in **one window**, tiled, at most **9** panes. All panes log in **at the same time**: a mistyped password is the user's
   problem, as when using tmux by hand.
5. You are now in tmux, with normal tmux controls. **`Ctrl-b d`** detaches and you're back in TRuffle. If you log out of all
   panes, the session ends and you're also back. `Ctrl-T` in TRuffle would reattach to the session.
6. **Batch ping** pings only the marked switches when some are marked (agreed, no tmux needed).
7. Inside an existing tmux (`$TMUX` set), tmux refuses nesting by default, so TRuffle would open a new **window** in the
   current session instead. Back with `Ctrl-b l`.
8. tmux's "type into all panes" (`synchronize-panes`) is forced **off** for this window.

## Handover channel (option 1)
Panes are started by tmux, not by TRuffle. Their command line is visible to every user (`ps`), so the password can't go
there, nor into environment variables or a file. Instead:
1. **Private folder:** TRuffle creates `$XDG_RUNTIME_DIR/truffle/` (`/run/user/<uid>`, in RAM, mode 0700, removed at
   logout; fallback `/tmp/truffle-<uid>`, owner and mode checked). In it, a Unix socket `handover-<pid>.sock` (0600).
2. **Ticket per pane:** a random 128-bit one-time ticket, passed on the pane's command line
   (`truffle --pane <socket> <ticket> <host> <name>`).
3. **Fetching the password:** the pane connects. The kernel reports the peer's uid and pid (`SO_PEERCRED`). TRuffle answers
   once with user and password if the uid is ours, the ticket is valid and unused, and the switch matches.
4. **Logging in:** the pane types the password like today (once, aborting on a second prompt) and forgets it.
5. **Reporting back:** at the end, the pane reports ok / failed / login failed via its ticket, so the SSH column and the
   recent list are updated, and the stored password is wiped on a login failure.

## Security assessment (Warden, brutally honest)
| Attacker | Gets the password? |
|---|---|
| Other users | no, if implemented correctly (folder, socket, kernel uid check) |
| Processes of the **same user** | without hardening yes (read a ticket from `ps`, race the pane). With pid binding they'd need to read process memory instead, and `PR_SET_DUMPABLE=0` blocks that too (built, D21) |
| root | yes, as with every tool |
| Network | no, Unix sockets are local only |

**The real, new risks:**
1. **New, self-written security code** (about 80 lines). This is the biggest risk. The pattern is proven (`ssh-agent`,
   `gpg-agent`), the implementation isn't. It should be reviewed before colleagues use it.
2. The password sits briefly in up to 9 more processes. Python can't reliably wipe memory.
3. Crash dumps could contain it. **Fixed for TRuffle already** (D21: core dumps off).
4. The ticket window between a pane starting and fetching. Closed by the hardening below.
5. **Forgotten background sessions (the Warden's main concern, shared by the user):** after `Ctrl-b d`, up to 9 logged-in
   admin sessions keep running until the switches' idle timeout. Requirements if built:
   - TRuffle shows **"N tmux sessions running"** prominently in the top bar
   - an **idle timeout** forgets the stored password
   - consider closing TRuffle's sessions when TRuffle exits (or asking)
6. **Company policy** may forbid passing credentials between processes. Check before rolling out.

**Mandatory hardening if built:**
- the ticket is bound to the **pane's process ID**: `tmux split-window -P -F "#{pane_pid}"`, compared with `SO_PEERCRED`'s
  pid or its parent
- ticket lifetime **10 s**
- the socket is open only while panes are starting, then closed and deleted
- core dumps off and not dumpable (already done for the main TRuffle)

## Alternatives (if option 1 is rejected)
- **Option 2:** same panes, but **each pane asks for the password itself**. No new attack surface, more typing.
- **Option 3:** no feature. Run two TRuffle copies in tmux by hand, which works today.

## Effort estimate
About 250–300 lines (marking, pane opener, `--pane` mode, handover, report-back) plus tests. tmux is installed on the
server, and the initiators use it.
