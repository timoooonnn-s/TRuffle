# Bracketed paste: a pasted newline must not launch an ssh session

**Status: UNDER DISCUSSION with the user (2026-10-04).** Nothing built.

## The problem, concretely

A terminal pastes by *typing* the text at the application - there is no "paste" event. TRuffle's
`read_key` therefore sees a pasted string one character at a time and cannot tell it from typing.

So if you copy a switch name out of a ticket, an e-mail or an Excel cell, the copy almost always
carries a **trailing newline** - and TRuffle reads that newline as `ENTER`:

1. the name lands in the search box, the list filters, fine
2. the newline arrives as `ENTER`
3. `ENTER` runs the selected command on the selected row - and `ssh` is selected by default
4. you are now looking at the login dialog for whatever row the filter happened to put first

Paste a *multi-line* list (three IPs from a ticket) and it is worse: every line runs `ENTER` again.
Other control characters in a paste do their own damage - a tab toggles a mark, an escape sequence
walks the command bar.

Nothing is destroyed (a connection is not a change) and the *Operator*'s point is not drama - it is
that the tool does something you did not ask for, at the moment you were just filling in a search
box, and the recovery is "log out of a switch you did not mean to open".

## What bracketed paste is

A terminal feature, not a library. The application turns it on by writing `ESC[?2004h`. From then
on the terminal wraps every paste in markers:

```
ESC[200~   <the pasted text, verbatim>   ESC[201~
```

The application can then treat everything between the markers as **literal text**, never as keys.
Turned off again with `ESC[?2004l`.

## How TRuffle would use it

- enable on start, disable on exit - and disable before handing the terminal to `ssh` or `tmux`
  and re-enable on the way back, so a switch session never inherits our terminal mode
- `parse_escape_sequence` already decodes `ESC[...~` sequences; add `[200~` -> `PASTE_START` and
  `[201~` -> `PASTE_END`
- between the two markers: append printable characters to the search and **drop everything else**
  (no `ENTER`, no `TAB`, no command switching). One refilter at the end instead of one per character
- a multi-line paste collapses to its first line, or the newlines become spaces (search terms are
  AND-ed anyway, so "10.0.0.1 10.0.0.2" sensibly matches nothing and you notice at once)

## Risk and fallback (*Critic*)

- A terminal that does not support it simply never sends the markers, so behaviour is exactly as
  today. There is no way for this to make anything worse.
- The *Critic* rejected the alternative of **guessing** from timing ("several characters inside
  N ms must be a paste"): over a laggy PuTTY link that misfires in both directions, and a tool that
  sometimes eats your `ENTER` is worse than one that sometimes acts on it.
- **Open question for the Researcher:** bracketed paste must be confirmed on *the team's actual
  PuTTY build* and in Tabby. Tabby is expected to support it. No version number is recorded here
  until someone has checked, and if PuTTY turns out not to support it the hazard stays there -
  this is then a Tabby-only improvement and should be judged as one.
- R1: no dependency. R2: pure escape sequences, identical on RHEL and macOS.

## Effort
~25 lines plus tests (the parser entries are one line each; the collecting is the rest).
