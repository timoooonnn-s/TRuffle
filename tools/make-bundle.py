#!/usr/bin/env python3
"""Pack TRuffle into ONE self-extracting text file, e.g. to send it by mail.

    python3 tools/make-bundle.py            ->  dist/truffle-bundle-<version>.py
    python3 tools/make-bundle.py --force    ->  rebuild even if that version exists already

The file name carries VERSION from truffle, so bump VERSION before building a bundle
whose contents changed - otherwise two different bundles would share one file name.

On the target machine:

    python3 truffle-bundle-<version>.py               # inside an existing copy / git checkout:
                                                      # update it in place; elsewhere: ./truffle
    python3 truffle-bundle-<version>.py /srv/truffle  # or into a directory of your choice
    python3 truffle-bundle-<version>.py --list        # only show what is inside

The bundle is plain ASCII (the files are a base64-encoded tar.gz), carries a SHA-256
checksum so a damaged attachment is detected, and never contains or overwrites
site files such as data.csv or truffle.conf - it can also be used to update.
Only files under version control are packed: commit new files before bundling.
Python 3.8+, standard library only.
"""

import base64
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Without git, only these project files are shipped.
ALLOW = re.compile(r"^(truffle|[^/]+\.md|data\.example\.csv|truffle\.conf\.example|\.git(ignore|attributes)"
                   r"|(tests|tools)/[^/]+\.py)$")
# Never shipped, even if tracked: site data, local settings, build output, caches.
# council/ holds the design notes of this workspace - it is not part of the deliverable.
EXCLUDE = re.compile(r"^council/|(^|/)(data\.csv|truffle\.conf|dist|\.git|__pycache__|\.DS_Store)(/|$)|\.pyc$|\.log$")

EXTRACTOR = r'''#!/usr/bin/env python3
"""TRuffle %(version)s - self-extracting bundle, created %(created)s.

    python3 %(name)s              in a folder that already holds TRuffle (e.g. your git
                                  checkout): update it in place; anywhere else: unpack into ./truffle
    python3 %(name)s TARGET_DIR   unpack / update exactly there
    python3 %(name)s --list       show the contents only

Files a newer version no longer has are removed - but only files a bundle installed
(listed in .truffle-files).  .git, data.csv, truffle.conf and your own files are never touched.
"""
import base64, hashlib, io, os, re, sys, tarfile

SHA256 = "%(sha256)s"
VERSION = "%(version)s"
MANIFEST = ".truffle-files"
PAYLOAD = """
%(payload)s
"""


def safe(name):
    return name and not name.startswith("/") and ".." not in name.split("/") and name != MANIFEST


def installed_version(folder):
    """VERSION of the truffle already in that folder, or None if there is none."""
    try:
        with open(os.path.join(folder, "truffle"), encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError:
        return None
    if "TRuffle" not in head:
        return None
    m = re.search(r'^VERSION = "([^"]+)"', head, re.M)
    return m.group(1) if m else "?"


def as_numbers(version):
    return [int(p) if p.isdigit() else 0 for p in re.split(r"[._-]", version or "")]


def main(argv):
    raw = base64.b64decode("".join(PAYLOAD.split()))
    if hashlib.sha256(raw).hexdigest() != SHA256:
        sys.exit("ERROR: the bundle is damaged (checksum mismatch) - please send it again.")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        members = tar.getmembers()
        for m in members:                   # only plain files with safe, relative names
            if not m.isfile() or not safe(m.name):
                sys.exit("ERROR: unexpected entry %%r in the bundle - not extracting." %% m.name)
        if argv[1:2] == ["--list"]:
            for m in members:
                print("%%8d  %%s" %% (m.size, m.name))
            return
        if len(argv) > 1:
            target = os.path.abspath(argv[1])
        elif installed_version(os.getcwd()):
            target = os.getcwd()            # run inside an existing copy: update it in place
        else:
            target = os.path.abspath("truffle")
        here = installed_version(target)
        print("TRuffle %%s -> %%s%%s\n" %% (VERSION, target, "   (replacing %%s)" %% here if here else ""))
        if here and as_numbers(here) > as_numbers(VERSION):
            print("  WARNING: %%s is already installed there - this bundle is OLDER (%%s)." %% (here, VERSION))
            if input("  Install the older version anyway? [y/N] ").strip().lower() != "y":
                print("  Nothing changed.")
                return
        try:
            with open(os.path.join(target, MANIFEST), encoding="utf-8") as f:
                previous = set(line.strip() for line in f if safe(line.strip()))
        except OSError:
            previous = set()
        unchanged = 0
        for m in members:
            path = os.path.join(target, *m.name.split("/"))
            data = tar.extractfile(m).read()
            mode = 0o755 if m.mode & 0o111 else 0o644
            try:
                with open(path, "rb") as f:
                    same = f.read() == data
            except OSError:
                same = None                 # new file
            if same:
                unchanged += 1
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as out:
                    out.write(data)
                print("  %%s %%s" %% ("updated" if same is False else "created", m.name))
            os.chmod(path, mode)
    names = set(m.name for m in members)
    for name in sorted(previous - names):   # dropped in this version - installed by a bundle before
        path = os.path.join(target, *name.split("/"))
        if os.path.isfile(path):
            os.remove(path)
            print("  removed %%s" %% name)
            folder = os.path.dirname(path)
            while folder != target and not os.listdir(folder):
                os.rmdir(folder)
                folder = os.path.dirname(folder)
    with open(os.path.join(target, MANIFEST), "w", encoding="utf-8") as f:
        f.write("".join(n + "\n" for n in sorted(names)))
    if unchanged:
        print("  %%d file(s) unchanged" %% unchanged)
    print("\nTRuffle %(version)s is in %%s" %% target)
    if not os.path.exists(os.path.join(target, "data.csv")):
        print("Next:  cd %%s && cp data.example.csv data.csv   (then add your switches)" %% target)
    if os.path.isdir(os.path.join(target, ".git")):
        print("Git:   cd %%s && git status   (then commit + push as usual)" %% target)
    print("Check: %%s --check" %% os.path.join(target, "truffle"))


if __name__ == "__main__":
    main(sys.argv)
'''


def project_files():
    """Only files under version control are shipped (git ls-files).  Other files in
    the folder - a copy of the switch list, notes - are listed, never packed.
    Without git: a fixed allow-list of the project's own files."""
    def git(*extra):
        out = subprocess.run(["git", "ls-files", "-z"] + list(extra), cwd=ROOT, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, check=True).stdout
        return [n for n in out.decode("utf-8").split("\0") if n]
    try:
        names = git("--cached")
        for extra in git("--others", "--exclude-standard"):
            print("  not included (not in git - commit it to ship it): %s" % extra)
    except (OSError, subprocess.CalledProcessError):
        names = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                name = os.path.relpath(os.path.join(base, f), ROOT).replace(os.sep, "/")
                if ALLOW.match(name):
                    names.append(name)
    return sorted(n for n in names if not EXCLUDE.search(n) and os.path.isfile(os.path.join(ROOT, n)))


def version():
    with open(os.path.join(ROOT, "truffle"), encoding="utf-8") as f:
        m = re.search(r'^VERSION = "([^"]+)"', f.read(), re.MULTILINE)
    return m.group(1) if m else "dev"


def existing_sha(path):
    """SHA-256 recorded inside a bundle that is already in dist/, or None."""
    try:
        with open(path, encoding="ascii", errors="replace") as f:
            m = re.search(r'^SHA256 = "([0-9a-f]+)"', f.read(4096), re.M)
        return m.group(1) if m else None
    except OSError:
        return None


def main():
    force = "--force" in sys.argv
    files = project_files()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in files:
            path = os.path.join(ROOT, name)
            info = tar.gettarinfo(path, arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
            with open(path, "rb") as f:
                tar.addfile(info, f)
    raw = buf.getvalue()
    payload = base64.b64encode(raw).decode("ascii")
    ver = version()
    digest = hashlib.sha256(raw).hexdigest()
    name = "truffle-bundle-%s.py" % ver
    text = EXTRACTOR % {
        "version": ver,
        "name": name,
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "sha256": digest,
        "payload": "\n".join(payload[i:i + 76] for i in range(0, len(payload), 76)),
    }
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", name)
    old = existing_sha(out)
    if old == digest:
        print("%s is already up to date (same contents)." % os.path.relpath(out, ROOT))
        return 0
    if old and not force:
        print("ERROR: dist/%s exists already and has DIFFERENT contents.\n"
              "       Two bundles must never share a file name - someone would install the wrong one.\n"
              "       Bump VERSION in truffle (now %s), then build again.  --force overrides."
              % (name, ver), file=sys.stderr)
        return 1
    with open(out, "w", encoding="ascii", newline="\n") as f:
        f.write(text)
    print("%d files -> %s (%d KB)" % (len(files), os.path.relpath(out, ROOT), (len(text) + 1023) // 1024))
    print("SHA-256 of the contents: %s" % digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
