#!/usr/bin/env python3
"""Replay file modifications from opencode sessions."""

import json
import os
from pathlib import Path

import fire
import sqlite_utils
import whatthepatch
from termcolor import cprint

DB = os.environ.get(
    "OPENCODE_DB", os.path.expanduser("~/.local/share/opencode/opencode.db")
)
TOOLS = ("edit", "write", "apply_patch")


def _db():
    if not os.path.exists(DB):
        raise SystemExit(f"DB not found: {DB}")
    import sqlite3 as _sqlite3

    return sqlite_utils.Database(_sqlite3.connect(f"file:{DB}?mode=ro", uri=True))


def _parse(item):
    name = item.get("tool") or item.get("name")
    if name not in TOOLS:
        return None
    st = item.get("state", {})
    if st.get("status") != "completed":
        return None
    inp, fp = st.get("input", {}), st.get("input", {}).get("filePath", "")
    if name == "write" and fp:
        return dict(t="w", f=fp, c=inp.get("content", ""))
    if name == "edit" and fp:
        return dict(t="e", f=fp, o=inp.get("oldString", ""), n=inp.get("newString", ""))
    if name == "apply_patch":
        patch, files = inp.get("patchText", ""), st.get("metadata", {}).get("files", [])
        if files:
            return [
                dict(t="p", f=fm.get("filePath", "?"), p=fm.get("patch", patch))
                for fm in files
            ]
        if patch:
            return dict(t="p", f="<patch>", p=patch)
    return None


def _add(mods, data, ts, sid):
    d = _parse(data)
    if not d:
        return
    for x in d if isinstance(d, list) else [d]:
        x["ts"] = ts
        x["sid"] = sid
        mods.append(x)


def _mods(db, sids):
    mods = []
    ph = ",".join("?" * len(sids))
    for r in db.query(
        f"SELECT p.session_id sid, p.data, m.time_created ts "
        f"FROM part p JOIN message m ON p.message_id=m.id "
        f"WHERE p.session_id IN ({ph}) ORDER BY m.time_created, p.id",
        sids,
    ):
        _add(
            mods,
            json.loads(r["data"]) if isinstance(r["data"], str) else r["data"],
            r["ts"],
            r["sid"],
        )
    try:
        for r in db.query(
            f"SELECT session_id sid, data, time_created ts "
            f"FROM session_message WHERE session_id IN ({ph}) AND type='assistant' "
            f"ORDER BY time_created, id",
            sids,
        ):
            msg = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
            for item in msg.get("content", []):
                if isinstance(item, dict):
                    _add(mods, item, r["ts"], r["sid"])
    except Exception:
        pass
    mods.sort(key=lambda m: (m["ts"], m["sid"]))
    return mods


def _write(fp, content):
    Path(fp).parent.mkdir(parents=True, exist_ok=True)
    Path(fp).write_text(content)


def replay(mods, dry_run=False):
    cache = {}
    for i, m in enumerate(mods, 1):
        fp = m["f"]
        cprint(f"  [{i}/{len(mods)}] ", "white", end="")
        cprint(
            {"w": "WRITE", "e": "EDIT", "p": "PATCH"}[m["t"]],
            {"w": "green", "e": "yellow", "p": "cyan"}[m["t"]],
            end="",
        )
        print(f" {fp}")
        if dry_run:
            continue
        if fp not in cache and os.path.exists(fp):
            cache[fp] = Path(fp).read_text(errors="replace")
        try:
            if m["t"] == "w":
                cache[fp] = m["c"]
                _write(fp, m["c"])
            elif m["t"] == "e":
                cur = cache.get(fp, "")
                if m["o"] in cur:
                    cache[fp] = cur.replace(m["o"], m["n"], 1)
                    _write(fp, cache[fp])
                else:
                    cprint("    SKIP: oldString not found", "red")
            elif m["t"] == "p":
                patch = next(whatthepatch.parse_patch(m["p"]), None)
                new = (
                    "\n".join(
                        whatthepatch.apply_diff(
                            patch, (cache.get(fp) or "").splitlines()
                        )
                    )
                    if patch
                    else None
                )
                if new is not None:
                    cache[fp] = new
                    _write(fp, new)
                else:
                    cprint("    SKIP: patch failed", "red")
        except Exception as e:
            cprint(f"    ERROR: {e}", "red")


def main(directory=None, list_dirs=False, dry_run=False):
    """Replay file modifications from opencode sessions."""
    db = _db()
    if list_dirs:
        for r in db.query("SELECT DISTINCT directory FROM session ORDER BY directory"):
            d = r["directory"]
            n = next(
                db.query(
                    "SELECT count(*) c FROM session WHERE directory=:d OR directory LIKE :d||'/'",
                    {"d": d},
                )
            )["c"]
            cprint(f"  {d}", "cyan", end="")
            print(f"  ({n} sessions)")
        return
    if not directory:
        print("Usage: opencode_replay.py DIRECTORY [--dry-run] [--list]")
        return
    sessions = list(
        db.query(
            "SELECT id, title FROM session WHERE directory=:d OR directory LIKE :d||'/' ORDER BY time_created",
            {"d": directory},
        )
    )
    if not sessions:
        raise SystemExit(f"No sessions for: {directory}")
    for s in sessions:
        cprint(f"  {s['title']}", "cyan", end="")
        print(f"  {s['id']}")
    mods = _mods(db, [s["id"] for s in sessions])
    cprint(f"\n{len(mods)} file modification(s)", attrs=["bold"])
    if mods:
        replay(mods, dry_run=dry_run)


if __name__ == "__main__":
    fire.Fire(main)
