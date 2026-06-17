#!/usr/bin/env python3
"""
Fix repeating text blocks in OpenCode session parts.

Finds parts in the SQLite database where the agent got stuck in a loop
(repeating the same phrases hundreds of times) and trims them down to
the meaningful content before the loop starts.

Usage:
    ./fix-repeating.py                    # Dry run - show what would be fixed
    ./fix-repeating.py --apply            # Apply fixes
    ./fix-repeating.py --apply --db /path/to/opencode.db  # Custom DB path
    ./fix-repeating.py --session ses_xxx  # Fix only parts in a specific session
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


DEFAULT_DB = Path.home() / ".local/share/opencode/opencode.db"

# Common phrases the agent repeats when stuck in a loop.
# Each pattern is a block of consecutive lines that indicates the loop.
REPEAT_BLOCKS = [
    (
        "Let me continue.\n\n"
        "Let me check the current bot status and run the integration tests.\n\n"
        "Let me proceed.\n\n"
        "Let me check the current bot status and test the commands.\n\n"
    ),
    (
        "Let me continue.\n\n"
        "Let me check the current bot status and run the integration tests.\n\n"
        "Let me proceed.\n\n"
        "Let me check the current bot status and test the commands.\n\n"
    ),
    (
        "Let me continue.\n\n"
        "Let me check the current bot status and run the integration tests.\n\n"
        "Let me proceed.\n\n"
        "Let me check if BotBeta is still connected or dead, and then test the commands.\n\n"
    ),
]


def find_loops(text: str) -> list[tuple[int, int, str]]:
    """
    Scan text for repeated blocks. Returns list of (start, end, pattern)
    where start..end is the repeating section.
    """
    results = []
    for pattern in REPEAT_BLOCKS:
        count = text.count(pattern)
        if count < 3:
            continue

        first_idx = text.find(pattern)
        if first_idx < 0:
            continue

        # Find where the loop ends: scan forward from first occurrence,
        # skip consecutive repeats.
        loop_start = first_idx
        idx = first_idx
        while True:
            next_idx = text.find(pattern, idx + len(pattern))
            # Allow small gaps (whitespace/newlines) between repeats
            gap = text[idx + len(pattern):next_idx] if next_idx >= 0 else ""
            if next_idx >= 0 and gap.strip() == "":
                idx = next_idx
            else:
                break

        loop_end = idx + len(pattern)
        results.append((loop_start, loop_end, pattern))

    # If no predefined patterns matched, try a generic approach:
    # find any line that repeats 10+ times
    if not results:
        lines = text.split("\n")
        from collections import Counter
        line_counts = Counter(lines)
        for line, count in line_counts.most_common():
            if count < 10 or len(line) < 20:
                continue
            # Find first and last occurrence
            first = text.find(line)
            last = text.rfind(line)
            if last > first + len(line):
                # Check if there's mostly just this line between first and last
                middle = text[first:last + len(line)]
                stripped = middle.replace(line, "").replace("\n", "").strip()
                if len(stripped) < len(middle) * 0.1:
                    results.append((first, last + len(line), line))

    return results


def analyze_part(part_id: str, message_id: str, data: str, session_id: str) -> dict | None:
    """Analyze a single part for repeating blocks."""
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return None

    text = parsed.get("text", "")
    if not text or len(text) < 500:
        return None

    loops = find_loops(text)
    if not loops:
        return None

    # Pick the largest loop
    largest = max(loops, key=lambda x: x[1] - x[0])
    start, end, pattern = largest
    removed = end - start

    return {
        "part_id": part_id,
        "message_id": message_id,
        "session_id": session_id,
        "original_length": len(text),
        "loop_start": start,
        "loop_end": end,
        "removed_chars": removed,
        "removed_pct": round(removed / len(text) * 100, 1),
        "pattern_preview": pattern[:80],
        "clean_text": text[:start].rstrip(),
    }


def main():
    parser = argparse.ArgumentParser(description="Fix repeating text blocks in OpenCode session parts")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to opencode.db")
    parser.add_argument("--apply", action="store_true", help="Apply fixes (default is dry run)")
    parser.add_argument("--session", type=str, help="Only fix parts in this session ID")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Error: Database not found at {args.db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db))
    cursor = conn.cursor()

    # Find parts with text data that are large enough to have loops
    query = "SELECT id, message_id, session_id, data FROM part WHERE data LIKE '%\"type\":\"text\"%' AND length(data) > 1000"
    if args.session:
        query += f" AND session_id = '{args.session}'"
    query += " ORDER BY length(data) DESC"

    cursor.execute(query)
    parts = cursor.fetchall()

    print(f"Scanning {len(parts)} parts for repeating blocks...\n")

    fixes = []
    for part_id, message_id, session_id, data in parts:
        result = analyze_part(part_id, message_id, data, session_id)
        if result:
            fixes.append(result)

    if not fixes:
        print("No repeating blocks found.")
        return

    print(f"Found {len(fixes)} parts with repeating blocks:\n")
    total_saved = 0
    for f in fixes:
        print(f"  Part: {f['part_id']}")
        print(f"  Session: {f['session_id']}")
        print(f"  Original: {f['original_length']:,} chars")
        print(f"  Loop: chars {f['loop_start']}-{f['loop_end']} ({f['removed_pct']}%)")
        print(f"  Pattern: {f['pattern_preview']}...")
        print(f"  Clean text preview: {f['clean_text'][-100:]}...")
        print()
        total_saved += f["removed_chars"]

    print(f"Total chars to remove: {total_saved:,}")

    if not args.apply:
        print("\nDry run. Use --apply to fix.")
        return

    # Apply fixes
    for f in fixes:
        new_data = json.dumps({"type": "text", "text": f["clean_text"]})
        cursor.execute("UPDATE part SET data = ? WHERE id = ?", (new_data, f["part_id"]))
        print(f"  Fixed {f['part_id']}: {f['original_length']:,} -> {len(new_data):,} chars")

    conn.commit()
    conn.close()
    print(f"\nDone. Applied {len(fixes)} fixes.")


if __name__ == "__main__":
    main()
