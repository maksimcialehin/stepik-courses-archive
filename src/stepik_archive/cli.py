"""CLI for listing, exporting, and searching Stepik course archives."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from stepik_archive.api import StepikAPIError, StepikClient
from stepik_archive.export import default_courses_dir, export_course


def cmd_list(_args: argparse.Namespace) -> int:
    client = StepikClient()
    try:
        courses = client.list_enrolled_courses()
    except StepikAPIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not courses:
        print("No enrolled courses found.")
        print(
            "Tip: set STEPIK_USERNAME and STEPIK_PASSWORD in .env "
            "(password grant) to see private/paid enrollments."
        )
        return 0

    courses = sorted(courses, key=lambda c: c.get("id", 0))
    for course in courses:
        cid = course.get("id")
        title = course.get("title", "")
        print(f"{cid}\t{title}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    client = StepikClient()
    output_dir = Path(args.output) if args.output else default_courses_dir()
    try:
        for course_id in args.course_ids:
            print(f"Exporting course {course_id}…")
            course_dir = export_course(
                client,
                course_id,
                output_dir=output_dir,
                include_all=args.include_all,
            )
            print(f"  → {course_dir}")
    except StepikAPIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def _search_with_rg(query: str, courses_dir: Path) -> int:
    cmd = [
        "rg",
        "-n",
        "-i",
        "--color",
        "always",
        "-g",
        "*.md",
        query,
        str(courses_dir),
    ]
    result = subprocess.run(cmd, check=False)
    return result.returncode if result.returncode in (0, 1) else result.returncode


def _search_fallback(query: str, courses_dir: Path) -> int:
    needle = query.lower()
    matches = 0
    for path in sorted(courses_dir.rglob("*.md")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            continue
        for lineno, line in enumerate(lines, start=1):
            if needle in line.lower():
                print(f"{path}:{lineno}:{line}")
                matches += 1
    return 0 if matches else 1


def cmd_search(args: argparse.Namespace) -> int:
    courses_dir = Path(args.path) if args.path else default_courses_dir()
    if not courses_dir.is_dir():
        print(f"Courses directory not found: {courses_dir}", file=sys.stderr)
        print("Run `stepik-archive export <course_id>` first.", file=sys.stderr)
        return 1

    if shutil.which("rg"):
        return _search_with_rg(args.query, courses_dir)
    print("ripgrep (rg) not found; using built-in search.", file=sys.stderr)
    return _search_fallback(args.query, courses_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stepik-archive",
        description="Export Stepik course theory to Markdown and search the archive.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List enrolled courses")
    list_parser.set_defaults(func=cmd_list)

    export_parser = sub.add_parser("export", help="Export course(s) to Markdown")
    export_parser.add_argument(
        "course_ids",
        nargs="+",
        type=int,
        help="Stepik course id(s)",
    )
    export_parser.add_argument(
        "-o",
        "--output",
        help="Output directory (default: ./courses or STEPIK_COURSES_DIR)",
    )
    export_parser.add_argument(
        "--include-all",
        action="store_true",
        help="Include non-text steps (still skips video)",
    )
    export_parser.set_defaults(func=cmd_export)

    search_parser = sub.add_parser("search", help="Search exported Markdown files")
    search_parser.add_argument("query", help="Search string")
    search_parser.add_argument(
        "-p",
        "--path",
        help="Archive directory (default: ./courses or STEPIK_COURSES_DIR)",
    )
    search_parser.set_defaults(func=cmd_search)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
