# Serial multi-connect: mark N switches, visit them one after another

**Status: UNDER DISCUSSION with the user (2026-10-04).** Nothing built.

## How it would be used

Marking stays exactly as it is today: **`Tab`** marks, **`Shift-Tab`** marks the row above,
**right-click** marks, **`ESC`** clears the marks, the top bar counts them.

With **2 or more marked** and `ssh` chosen, TRuffle asks which way to go - one small window,
the same one `Ctrl-K` already uses:

```
  ╭─ 7 switches marked ─────────────────────────────╮
  │  p   all at once, one tmux pane each (max 9)    │
  │  s   one after another, here in TRuffle         │
  │  ESC cancel                                     │
  ╰─────────────────────────────────────────────────╯
```

With `s`, TRuffle connects to the first marked switch exactly as a single `ssh` does today.
When you log out, it does not go back to the list - it shows the step screen:

```
  TRuffle  ›  3 of 7 done                     timmy

    done      ber-core-01   logged out
    done      ber-core-02   logged out
    failed    ber-dist-01   Connection timed out
  > next      ber-dist-02   10.0.3.12

  Enter connect   s skip   b back to the list   q stop
```

| Key | Does |
|---|---|
| `Enter` | connect to the switch on the `>` line |
| `s` | skip it (stays marked, counted as skipped) |
| `b` | leave the queue, back to the normal list, marks kept |
| `q` | drop the queue and the marks |
| `ESC` | same as `b` |

The password is asked once, as always. Failures do not stop the queue; they are listed and you
move on. At the end: "6 connected, 1 failed, 0 skipped" and the SSH column is filled in for all
of them. There is no auto-advance: *every* connection needs an `Enter`, so a 20-switch queue can
never run away from you.

## Is it compatible with tmux mode?

**Yes, fully, and it does not touch any of the tmux code.** They are two ways to spend the same
marks, chosen in the window above; the config option `tmux = no` simply removes the `p` choice
and goes straight to serial. Serial mode uses no tmux, no socket, no ticket, no handover - it is
the existing single-session code path (`ssh_flow`) in a loop.

One extra benefit: it also works when **TRuffle itself runs inside tmux**, where the pane feature
has to do the `switch-client` dance because tmux refuses to nest.

## What it ACTUALLY solves over tmux mode - brutally honest

**Real wins:**
1. **More than 9 switches.** Panes are capped at 9 for readability. Mark 20 today and 11 are
   dropped (now reported, still dropped). A queue has no cap.
2. **Nothing stays logged in.** This is the Warden's main concern from
   [tmux-panes.md](tmux-panes.md) risk 5: after `Ctrl-b d`, up to 9 admin sessions sit there until
   the switches' idle timeout. A queue holds exactly one session, and it is the one on your screen.
3. **No new attack surface.** No handover, none of the ~80 lines of self-written security code
   whose review is still the open merge gate, and nothing for company policy (risk 6) to object to.
   If that policy answer ever comes back "no", serial mode is the multi-switch feature that survives.
4. **Readable on a real terminal.** 9 panes in an 80x24 PuTTY window are 9 tiny boxes. For "run one
   command on 15 switches and actually read the output", one full-screen session at a time is better.

**Now the honest part - why this may not be worth building:**
1. **It is mostly possible today.** Enter, log out, `↓`, Enter. The queue saves you re-finding your
   place in a filtered list and gives you a summary at the end. That is a convenience, not a new
   capability. Be clear-eyed: the saving is a handful of keystrokes per switch.
2. **For 2-4 switches, tmux is simply better** and that is probably the common case. Side by side
   beats one after another whenever you want to *compare* something live. Serial mode does not
   replace panes and must not be sold as doing so.
3. **It overlaps badly with the read-only command runner idea.** If "run `show ...` on N switches
   and collect the output" ever gets built, that automates the exact job people would use a manual
   queue for, and serial mode's value drops a lot. Building both is duplicated effort.
4. **One more choice in the way.** Today `ssh` with marks does one thing. This adds a window
   between you and the connection, every time. The *Operator* only accepts that because the window
   is also where "you marked 20, only 9 fit" stops being a silent surprise.

**The Drafter's reading:** build it only if you really work through *lists* of switches by hand -
"walk these 14 and check one thing". If your actual habit is 2-4 switches side by side, tmux mode
already covers you and this is bloat. That question is the user's, not the council's.

## Effort
~60-80 lines (the chooser window, the queue, the step screen) plus tests. No new dependencies
(R1), no platform-specific code (R2). Reuses `ssh_flow`, `draw_window` and the marks.
