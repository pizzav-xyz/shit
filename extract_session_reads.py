#!/usr/bin/env python3
"""
Extract the latest Read tool outputs from a session markdown file
and restore files to their correct locations in the working directory.

When files are truncated, combines their contents from multiple reads
(using offset/limit) to reconstruct complete file contents.

Usage:
    python extract_session_reads.py <session_file.md> [cwd]

Examples:
    python extract_session_reads.py session-ses_2a4c.md
    python extract_session_reads.py session-ses_2a4c.md /home/pizzav/Documents/ShulkerV2beta-python
"""

import re
import json
import os
import sys


def extract_reads(session_path, cwd):
    """Extract all Read tool outputs from session markdown, combining truncated reads."""
    with open(session_path, "r", encoding="utf-8") as f:
        text = f.read()

    pattern = re.compile(
        r"\*\*Tool: read\*\*\s+"
        r"\*\*Input:\*\*\s+```json\s+({.*?})\s+```\s+"
        r"\*\*Output:\*\*\s+```\s+(.*?)```",
        re.DOTALL,
    )

    file_reads: dict[str, list] = {}
    stats = {"complete": 0, "truncated": 0, "skipped": 0, "combined": 0}

    for m in pattern.finditer(text):
        input_json = m.group(1)
        output = m.group(2).strip()

        try:
            inp = json.loads(input_json)
            filepath = inp.get("filePath", "")
        except json.JSONDecodeError:
            continue

        if not filepath.startswith(cwd):
            continue

        content_match = re.search(r"<content>(.*?)</content>", output, re.DOTALL)
        if not content_match:
            continue

        raw = content_match.group(1)
        lines = raw.split("\n")

        line_data = []
        for line in lines:
            line_match = re.match(r"^(\d+):\s?(.*)", line)
            if line_match:
                line_num = int(line_match.group(1))
                line_content = line_match.group(2)
                line_data.append((line_num, line_content))

        if not line_data:
            continue

        start_line = line_data[0][0]
        end_line = line_data[-1][0]
        clean_content = "\n".join(content for _, content in line_data)

        rel = filepath.replace(cwd.rstrip("/") + "/", "")

        is_complete = "(End of file" in output
        status = "COMPLETE" if is_complete else "TRUNCATED"
        if is_complete:
            stats["complete"] += 1
        else:
            stats["truncated"] += 1

        print(
            f"  [{status}] {rel} lines {start_line}-{end_line} ({len(clean_content)} chars)"
        )

        if rel not in file_reads:
            file_reads[rel] = []

        file_reads[rel].append(
            {
                "start_line": start_line,
                "end_line": end_line,
                "content": clean_content,
                "is_complete": is_complete,
            }
        )

    return file_reads, stats


def combine_reads(reads_list):
    """Combine multiple reads of the same file into a single content string.

    Strategy:
    1. If any read is complete, prefer it (latest complete read wins).
    2. Otherwise, combine truncated reads by line range, using the latest
       read for any overlapping lines.
    """
    complete_reads = [r for r in reads_list if r["is_complete"]]
    if complete_reads:
        return complete_reads[-1]["content"], True

    line_map = {}
    max_line = 0

    for read_entry in reads_list:
        start = read_entry["start_line"]
        lines = read_entry["content"].split("\n")
        for i, line_content in enumerate(lines):
            line_num = start + i
            line_map[line_num] = line_content
            max_line = max(max_line, line_num)

    if not line_map:
        return "", False

    combined_lines = []
    for line_num in range(min(line_map.keys()), max_line + 1):
        if line_num in line_map:
            combined_lines.append(line_map[line_num])
        else:
            combined_lines.append(f"# [MISSING LINE {line_num}]")

    return "\n".join(combined_lines), False


def write_files(file_reads, cwd):
    """Write extracted files to their correct locations, combining truncated reads."""
    written = []

    for rel, reads_list in sorted(file_reads.items()):
        content, is_complete = combine_reads(reads_list)

        if len(reads_list) > 1 and not is_complete:
            print(f"  [COMBINED] {rel} ({len(reads_list)} reads merged)")

        outpath = os.path.join(cwd, rel)
        os.makedirs(os.path.dirname(outpath), exist_ok=True)

        with open(outpath, "w", encoding="utf-8") as f:
            f.write(content)

        actual_size = os.path.getsize(outpath)
        written.append((rel, actual_size, is_complete))
        tag = "✓" if is_complete else "⚠"
        print(f"  {tag} {rel} -> {actual_size} bytes")

    return written


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    session_path = sys.argv[1]
    cwd = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

    if not os.path.isfile(session_path):
        print(f"Error: Session file not found: {session_path}")
        sys.exit(1)

    print(f"Reading: {session_path}")
    print(f"Target:  {cwd}\n")

    file_reads, stats = extract_reads(session_path, cwd)

    combined_count = sum(1 for reads in file_reads.values() if len(reads) > 1)

    print(f"\n--- Read stats ---")
    print(f"  Complete reads:  {stats['complete']}")
    print(f"  Truncated reads: {stats['truncated']}")
    print(f"  Unique files:    {len(file_reads)}")
    print(f"  Files combined:  {combined_count}")

    print(f"\n--- Writing files ---")
    written = write_files(file_reads, cwd)

    truncated = [r for r in written if not r[2]]
    if truncated:
        print(f"\n⚠  {len(truncated)} file(s) still incomplete after combining:")
        for rel, size, _ in truncated:
            print(f"    - {rel}")

    print(f"\nDone. {len(written)} files restored.")


if __name__ == "__main__":
    main()
