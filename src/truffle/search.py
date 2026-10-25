"""The search language (README "Search"; D12, D16, D34, D39): every space-separated term
must match.  word = fuzzy, split only at separators; 'word = exact; * ? = pattern over a
whole column; field:value; ping:/ssh:/is:; -term excludes; a|b = either, inside one term."""

import fnmatch

from .inventory import BOUNDARY, IPV4_LIKE, segments_of

NO_BOUNDARY = str.maketrans("", "", BOUNDARY)
NO_FIELD_SEP = str.maketrans("", "", " _-")
WILDCARD = "*?"
STATE_FIELDS = ("is", "ping", "ssh")


# -- fuzzy words ---------------------------------------------------------------

def anchored_positions(pattern, segments):
    """The positions where pattern covers the text, or None.  The first chunk may sit
    anywhere in a segment, every later one must START a later segment (D39): bc01 finds
    ber-core-01, w4 does not find wx-x4-sxx-xx."""
    failed = set()

    def cover(pi, si, first):
        if pi == len(pattern):
            return []
        if (pi, si, first) in failed:
            return None
        for s in range(si, len(segments)):
            offset, part = segments[s]
            for o in (range(len(part)) if first else (0,)):
                longest = min(len(part) - o, len(pattern) - pi)
                for length in range(longest, 0, -1):     # longest chunk first: tighter match
                    if part[o:o + length] == pattern[pi:pi + length]:
                        rest = cover(pi + length, s + 1, False)
                        if rest is not None:
                            return list(range(offset + o, offset + o + length)) + rest
        failed.add((pi, si, first))
        return None

    return cover(0, 0, True)


def score_positions(text, positions):
    """How good a match is: a letter at the start of a segment counts, and so does
    every letter that follows directly on the one before."""
    score, previous = 0, None
    for pos in positions:
        score += 1
        if pos == 0 or text[pos - 1] in BOUNDARY:
            score += 8
        if previous is not None:
            score += 5 if pos == previous + 1 else -min(3, pos - previous - 1)
        previous = pos
    return score


def fuzzy_match(pattern, text, segments=None):
    """(score, positions) or None, both strings lower case.  Written together = found
    anywhere and best; otherwise anchored_positions.  segments: precomputed, hot path."""
    i = text.find(pattern)
    if i >= 0:                                   # written together: always the best match
        bonus = 30 if i == 0 or text[i - 1] in BOUNDARY else 0
        return 1000 + 2 * len(pattern) + bonus, tuple(range(i, i + len(pattern)))
    squeezed = pattern.translate(NO_BOUNDARY)
    if not squeezed or not set(squeezed) <= set(text):
        return None                              # nothing to search for, or a letter is missing
    positions = anchored_positions(squeezed, segments_of(text) if segments is None else segments)
    if positions is None:
        return None
    return score_positions(text, positions), tuple(positions)


def fuzzy_term(word):
    """Test for one search word: the best-matching visible column wins.  The test
    returns (score, column, positions) or None."""
    def test(d):
        best = None
        for i, cell in enumerate(d.lcells):
            m = fuzzy_match(word, cell, d.lsegments[i])
            if m and (best is None or m[0] > best[0]):
                best = (m[0], i, m[1])
        return best
    return test


# -- patterns ------------------------------------------------------------------

def has_wildcard(text):
    return any(c in text for c in WILDCARD)


def glob_match(value, pattern):
    """The pattern must match the WHOLE value (*-l1 is not *-l11).  For names the part
    before the first dot counts too (FQDNs), for addresses not: 19? is not 192.0.2.98."""
    if fnmatch.fnmatchcase(value, pattern):
        return True
    head = value.split(".", 1)[0]
    return head != value and not IPV4_LIKE.match(value) and fnmatch.fnmatchcase(head, pattern)


def glob_term(pattern):
    """A word containing * or ? is a pattern over one whole visible column."""
    return lambda d: any(glob_match(cell, pattern) for cell in d.lcells)


# -- exact terms and fields ----------------------------------------------------

def status_term(states, value):
    """ping:/ssh: filters.  'none' (and a bare 'ping:', like any other empty field:)
    = not checked yet, otherwise the start of a state."""
    if value in ("", "none"):
        return lambda d: d.host not in states
    return lambda d: d.host in states and states[d.host].startswith(value)


class Fields(dict):
    """lower-case header or label -> CSV header, for field:value.  `labels` are the
    names from `columns` - the ones you gave the columns, so they win a short name."""

    def __init__(self, headers=(), columns=()):
        dict.__init__(self, ((h.lower(), h) for h in headers))
        self.update((label.lower(), h) for h, label in columns)
        self.labels = dict((label.lower(), h) for h, label in columns)


def field_header(name, fields):
    """The CSV header a field name means, or None.  The whole name, a header or a label
    from `columns`; or the start of ONE column's name, spaces and _ - left out, so
    loc: is LOCATION and site_name: is "Site Name" (D49).  Your labels are asked first;
    a start that still fits two columns means neither - then it is plain text."""
    if name in fields:
        return fields[name]
    squeezed = name.translate(NO_FIELD_SEP)
    if len(squeezed) < 2:
        return None
    for names in (getattr(fields, "labels", {}), fields):
        hits = set(h for f, h in names.items() if f.translate(NO_FIELD_SEP).startswith(squeezed))
        if len(hits) == 1:
            return hits.pop()
        if hits:
            return None
    return None


def field_value_match(value, cell):
    """field:value - contained in the cell, or found like a plain word in it (bc01 in
    ber-core-01), so a field narrows the search without making it stricter (D49)."""
    return value in cell or fuzzy_match(value, cell) is not None


def exact_term(token, fields, status, recent, marked=(), exact=False):
    """Every non-fuzzy term -> test function returning True / False.  exact: the field
    value is matched as plain text only - for 'exact, and for an exclude (D16: a
    forgiving exclude hides far too much)."""
    name, sep, value = token.partition(":")
    if sep:
        if name == "is":
            collection = {"recent": recent, "marked": marked}.get(value)
            if collection is not None:
                return lambda d: d.key in collection
        if name in ("ping", "ssh"):
            return status_term(status.get(name, {}), value)
        header = field_header(name, fields)
        if header is not None:
            if not value:
                return lambda d: not d.values.get(header)
            if has_wildcard(value):      # name:*-l1 is a pattern over that column
                return lambda d: glob_match(d.values.get(header, "").lower(), value)
            if exact:
                return lambda d: value in d.values.get(header, "").lower()
            return lambda d: field_value_match(value, d.values.get(header, "").lower())
    # plain text - also unknown "x:y" such as IPv6 addresses
    return lambda d: token in d.search


def known_field(text, fields):
    """True when text starts with a field: prefix TRuffle knows about."""
    name, sep, _ = text.partition(":")
    return bool(sep) and (name in STATE_FIELDS or field_header(name, fields or {}) is not None)


def field_hint(query, fields):
    """'location:berlin' when the query has a column name followed by a word
    ("LOCATION berlin" - a space where the colon belongs), else None."""
    tokens = query.split()
    for name, value in zip(tokens, tokens[1:]):
        if ":" not in name and name.lower() in fields and name.lower() not in STATE_FIELDS:
            return "%s:%s" % (name, value)
    return None


def alternatives(token, fields):
    """One term split on '|'; a bare alternative inherits the first one's field: prefix
    (ping:up|wait = up or wait)."""
    parts = [p for p in token.split("|") if p]
    if not parts:
        return []
    prefix = ""
    if known_field(parts[0], fields):
        prefix = parts[0].partition(":")[0] + ":"
    return [parts[0]] + [p if known_field(p, fields) else prefix + p for p in parts[1:]]


# -- the whole query -----------------------------------------------------------

def compile_query(query, fields, status, recent, marked):
    """The query -> [(negate, [(fuzzy, test), ...])]: one entry per term, ALL must hold,
    and inside a term ANY alternative."""
    terms = []
    for token in query.lower().split():
        if token.strip("'-|") == "":                 # just started typing a term: no filter yet
            continue
        negate = len(token) > 1 and token.startswith("-")
        if negate:
            token = token[1:]
        alts = []
        for alt in alternatives(token, fields):
            if alt.startswith("'") and len(alt) > 1:
                alts.append((False, exact_term(alt[1:], fields, status, recent, marked, exact=True)))
            elif known_field(alt, fields) or (negate and not has_wildcard(alt)):
                # an excluded word stays exact: a fuzzy exclude hides far too much (D16)
                alts.append((False, exact_term(alt, fields, status, recent, marked, exact=negate)))
            elif has_wildcard(alt):
                alts.append((False, glob_term(alt)))
            else:
                alts.append((True, fuzzy_term(alt)))
        if alts:
            terms.append((negate, alts))
    return terms


def match_device(d, terms):
    """None when d fails a term, else (score, {column: positions}) of its fuzzy words."""
    score, marks = 0, {}
    for negate, alts in terms:
        hit, best = False, None
        for fuzzy, test in alts:
            result = test(d)
            if fuzzy:
                if result is not None:
                    hit = True
                    if best is None or result[0] > best[0]:
                        best = result       # the best-scoring alternative is highlighted
            elif result:
                hit = True
        if hit == negate:
            return None
        if best is not None:
            score += best[0]
            marks.setdefault(best[1], set()).update(best[2])
    return score, marks


def filter_devices(devices, query, fields=None, status=None, recent=None, found=None,
                   marked=()):
    """The devices matching every term, in their order.  status: {"ping": {host: state}, ...};
    found (a dict) receives device -> (score, {column: positions}) of fuzzy words."""
    terms = compile_query(query, fields or {}, status or {}, recent or {}, marked)
    if not terms:
        return list(devices)
    out = []
    for d in devices:
        match = match_device(d, terms)
        if match is None:
            continue
        out.append(d)
        if found is not None and match[1]:
            found[d] = match
    return out


def default_order(view, query, recent, found=None):
    """Order without a chosen sort column: newest first for is:recent; with fuzzy words
    the best matches first; otherwise the CSV order."""
    if "is:recent" in query.lower().split():
        return sorted(view, key=lambda d: recent.get(d.key, 0), reverse=True)
    if found:
        view = sorted(view, key=lambda d: -found.get(d, (0,))[0])    # stable: CSV order on ties
    return view
