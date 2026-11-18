"""Export Stepik courses to a local Markdown tree."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stepik_archive.api import StepikClient
from stepik_archive.convert import html_to_markdown, numbered_name, safe_filename

# Theory steps. Assignments use other block names (code, choice, matching, …).
THEORY_BLOCK = "text"
SKIP_ALWAYS = {"video"}


def default_courses_dir() -> Path:
    env = os.getenv("STEPIK_COURSES_DIR")
    if env:
        return Path(env)
    return Path.cwd() / "courses"


def _should_keep_step(block_name: str, include_all: bool) -> bool:
    if block_name in SKIP_ALWAYS:
        return False
    if include_all:
        return True
    return block_name == THEORY_BLOCK


def _block_to_markdown(block: dict[str, Any]) -> str:
    name = block.get("name", "")
    parts: list[str] = []

    text_html = block.get("text")
    if text_html:
        parts.append(html_to_markdown(text_html))

    # Some non-text blocks still carry a prompt in `text`; for include-all
    # also surface source/code snippets when present.
    if name == "code":
        source = (block.get("source") or {}).get("template_python") or (
            block.get("source") or {}
        ).get("template")
        if isinstance(source, str) and source.strip():
            parts.append(f"```\n{source.rstrip()}\n```")

    return "\n\n".join(p for p in parts if p).strip()


def export_course(
    client: StepikClient,
    course_id: int,
    output_dir: Path | None = None,
    include_all: bool = False,
) -> Path:
    """Export one course. Returns path to the course directory."""
    root = output_dir or default_courses_dir()
    course = client.fetch_object("course", course_id)
    course_title = course.get("title") or f"course_{course_id}"
    course_dir = root / f"{str(course_id).zfill(3)}_{safe_filename(course_title)}"
    course_dir.mkdir(parents=True, exist_ok=True)

    sections = client.fetch_objects("section", course.get("sections") or [])
    meta_lessons: list[dict[str, Any]] = []
    exported_steps = 0
    skipped_steps = 0

    for section in sorted(sections, key=lambda s: s.get("position", 0)):
        section_pos = section.get("position", 0)
        section_title = section.get("title") or f"section_{section_pos}"
        section_dir = course_dir / numbered_name(section_pos, section_title)
        section_dir.mkdir(parents=True, exist_ok=True)

        units = client.fetch_objects("unit", section.get("units") or [])
        for unit in sorted(units, key=lambda u: u.get("position", 0)):
            unit_pos = unit.get("position", 0)
            lesson = client.fetch_object("lesson", unit["lesson"])
            lesson_title = lesson.get("title") or f"lesson_{unit_pos}"
            lesson_path = section_dir / f"{numbered_name(unit_pos, lesson_title)}.md"

            steps = client.fetch_objects("step", lesson.get("steps") or [])
            steps = sorted(steps, key=lambda s: s.get("position", 0))

            md_parts: list[str] = [f"# {lesson_title}", ""]
            lesson_step_ids: list[int] = []

            for step in steps:
                # step.block is what learners see; step-sources is author-only (403).
                block = step.get("block") or {}
                block_name = block.get("name", "")
                if not _should_keep_step(block_name, include_all):
                    skipped_steps += 1
                    continue

                body = _block_to_markdown(block)
                if not body:
                    skipped_steps += 1
                    continue

                position = step.get("position", 0)
                md_parts.append(f"## Step {position} ({block_name})")
                md_parts.append("")
                md_parts.append(body)
                md_parts.append("")
                lesson_step_ids.append(step["id"])
                exported_steps += 1

            if lesson_step_ids:
                lesson_path.write_text("\n".join(md_parts).rstrip() + "\n", encoding="utf-8")
                meta_lessons.append(
                    {
                        "lesson_id": lesson["id"],
                        "unit_position": unit_pos,
                        "title": lesson_title,
                        "path": str(lesson_path.relative_to(course_dir)),
                        "step_ids": lesson_step_ids,
                    }
                )
            elif lesson_path.exists():
                # Re-export with stricter filter: remove stale empty lesson file
                lesson_path.unlink()

    meta = {
        "course_id": course_id,
        "title": course_title,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "include_all": include_all,
        "exported_steps": exported_steps,
        "skipped_steps": skipped_steps,
        "lessons": meta_lessons,
    }
    (course_dir / "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return course_dir
