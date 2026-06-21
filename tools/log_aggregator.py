#!/usr/bin/env python3
"""Log aggregator with parse-error reporting."""
import argparse
import json
import os
from datetime import datetime, timezone
from typing import Dict, List


def parse_log_file(file_path: str) -> tuple[list, List[Dict]]:
    """Parse a log file, returning records and parse errors."""
    records, errors = [], []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                errors.append({
                    "line": line_num,
                    "error_type": "json_decode_error",
                    "message": str(e).split(":")[0]
                })
    return records, errors


def generate_error_report(file_errors: Dict[str, List[Dict]]) -> Dict:
    """Generate sanitized error report without leaking payloads."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_failures": sum(len(e) for e in file_errors.values()),
        "files_with_errors": len(file_errors),
        "failures": [
            {"file": fp, "error_count": len(errs), "errors": errs}
            for fp, errs in file_errors.items()
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Log aggregator")
    parser.add_argument("input_files", nargs="+", help="Log files to parse")
    parser.add_argument("--parse-error-report", metavar="PATH",
                        help="Write JSON parse error report to PATH")
    args = parser.parse_args()

    all_records, file_errors = [], {}
    for fp in args.input_files:
        if not os.path.isfile(fp):
            print(f"Warning: {fp} not found, skipping")
            continue
        records, errors = parse_log_file(fp)
        all_records.extend(records)
        if errors:
            file_errors[fp] = errors

    print(f"Parsed {len(all_records)} records from {len(args.input_files)} files")

    if args.parse_error_report:
        report = generate_error_report(file_errors)
        with open(args.parse_error_report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Parse error report written to: {args.parse_error_report}")


if __name__ == "__main__":
    main()
