from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
MANIFEST = ROOT / "school_structure_navigation_manifest.json"
MARKER = "school-structure-navigation"


def render(page: dict) -> str:
    parent = page["parent"]
    items = [
        '<li class="link-card"><a class="text-link" '
        f'href="{html.escape(parent["href"], quote=True)}">'
        f'<span>{html.escape(parent["label"])}</span>'
        '<small>상위 학교 페이지 보기</small></a></li>'
    ]
    for href in page["children"]:
        items.append(
            '<li class="link-card"><a class="text-link" '
            f'href="{html.escape(href, quote=True)}">'
            f'<span>{html.escape(href.strip("/"))}</span>'
            '<small>세부 학교 페이지 보기</small></a></li>'
        )
    return (
        '        <section class="section page-section school-structure-navigation">\n'
        '          <h2>학교 학습 구조 탐색</h2>\n'
        '          <p class="section-note">상위 페이지와 현재 페이지에서 이어지는 세부 학습 페이지를 확인할 수 있습니다.</p>\n'
        f'          <ul class="link-list">{"".join(items)}</ul>\n'
        '        </section>'
    )


def main() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pages = payload["pages"]
    if payload["school_count"] != 241 or payload["page_count"] != 2892 or len(pages) != 2892:
        raise RuntimeError("school navigation manifest count mismatch")

    changed = 0
    unchanged = 0
    broken = 0
    duplicate_href = 0
    roots = 0
    for page in pages:
        path = OUTPUT / page["path"]
        if not path.is_file():
            raise RuntimeError(f'school page missing: {page["path"]}')
        hrefs = [page["parent"]["href"], *page["children"]]
        duplicate_href += len(hrefs) - len(set(hrefs))
        for href in hrefs:
            target = OUTPUT / href.strip("/") / "index.html"
            if not target.is_file():
                broken += 1
        roots += page["root"]

        text = path.read_text(encoding="utf-8")
        section = render(page)
        if MARKER in text:
            patched, count = re.subn(
                r'        <section class="section page-section school-structure-navigation">.*?</section>',
                section,
                text,
                count=1,
                flags=re.S,
            )
            if count != 1:
                raise RuntimeError(f'existing navigation count mismatch: {page["path"]}')
        else:
            patched, count = re.subn(
                r'        <section class="section page-section">\s*<h2>관련 상위 페이지</h2>.*?</section>',
                section,
                text,
                count=1,
                flags=re.S,
            )
            if count != 1:
                raise RuntimeError(f'navigation insertion target missing: {page["path"]}')
        if patched == text:
            unchanged += 1
        else:
            path.write_text(patched, encoding="utf-8")
            changed += 1

    if roots != 241 or broken or duplicate_href:
        raise RuntimeError(f"school navigation validation failed: roots={roots}, broken={broken}, duplicate_href={duplicate_href}")
    print(json.dumps({"pages": len(pages), "roots": roots, "changed": changed, "unchanged": unchanged, "broken": broken, "duplicate_href": duplicate_href}, ensure_ascii=False))


if __name__ == "__main__":
    main()
