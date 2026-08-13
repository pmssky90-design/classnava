from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
MANIFEST = ROOT / "region_expansion_navigation_manifest.json"
MARKER = "region-expansion-navigation"


def parent_section(children: list[dict[str, str]]) -> str:
    links = "".join(
        f'<li class="link-card"><a class="text-link" href="/{child["slug"]}/">'
        f'<span>{html.escape(child["title"])}</span>'
        f'<small>지역 세부 학습 페이지 보기</small></a></li>'
        for child in children
    )
    return (
        f'        <section class="section page-section {MARKER}" data-navigation-version="20260813">\n'
        '          <h2>이 지역의 신규 학습 콘텐츠</h2>\n'
        '          <p class="section-note">이 지역에 실제 존재하는 학년·과목별 학습 콘텐츠를 확인할 수 있습니다.</p>\n'
        f'          <ul class="link-list">{links}</ul>\n'
        '        </section>\n\n'
    )


def patch_parent(entry: dict) -> bool:
    path = ROOT / entry["path"]
    text = path.read_text(encoding="utf-8")
    if text.count(MARKER) == 1:
        return False
    if MARKER in text:
        raise RuntimeError(f"duplicate parent marker: {entry['path']}")
    patched, count = re.subn(r"(\s*</article>)", "\n" + parent_section(entry["children"]) + r"\1", text, count=1)
    if count != 1:
        raise RuntimeError(f"parent insertion target missing: {entry['path']}")
    path.write_text(patched, encoding="utf-8")
    return True


def patch_child(entry: dict) -> bool:
    path = ROOT / entry["path"]
    text = path.read_text(encoding="utf-8")
    href = f'href="/{entry["parent_slug"]}/"'
    if href in text:
        return False
    replacement = (
        r'\1<li class="link-card"><a class="text-link" href="/'
        + entry["parent_slug"]
        + '/"><span>'
        + html.escape(entry["parent_slug"])
        + '</span><small>상위 지역 페이지 보기</small></a></li>\2'
    )
    patched, count = re.subn(
        r'(<h2>관련 상위 페이지</h2>\s*<ul class="link-list">).*?(</ul>)',
        replacement,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError(f"child parent section missing: {entry['path']}")
    path.write_text(patched, encoding="utf-8")
    return True


def validate(entries: list[dict]) -> None:
    for entry in entries:
        path = ROOT / entry["path"]
        text = path.read_text(encoding="utf-8")
        if entry["kind"] == "parent":
            if text.count(MARKER) != 1:
                raise RuntimeError(f"invalid parent marker count: {entry['path']}")
            for child in entry["children"]:
                if text.count(f'href="/{child["slug"]}/"') != 1:
                    raise RuntimeError(f"invalid child href count: {entry['path']} -> {child['slug']}")
                if not (OUTPUT / child["slug"] / "index.html").is_file():
                    raise RuntimeError(f"child output missing: {child['slug']}")
        elif text.count(f'href="/{entry["parent_slug"]}/"') != 1:
            raise RuntimeError(f"invalid parent href count: {entry['path']}")


def main() -> None:
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    changed = 0
    for entry in entries:
        changed += patch_parent(entry) if entry["kind"] == "parent" else patch_child(entry)
    validate(entries)
    print(f"Region expansion navigation patch complete: entries={len(entries)}, changed={changed}")


if __name__ == "__main__":
    main()
