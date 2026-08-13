from __future__ import annotations
import html, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
MANIFEST = ROOT / "structure_region_navigation_manifest.json"
MARKER = "school-region-navigation"

def section(slugs: list[str]) -> str:
    links = "".join(f'<li class="link-card"><a class="text-link" href="/{s}/"><span>{html.escape(s)}</span><small>학교 과외 페이지 보기</small></a></li>' for s in sorted(slugs))
    return f'        <section class="section page-section {MARKER}" data-structure-version="20260813">\n          <h2>이 지역의 고등학교 과외</h2>\n          <p class="section-note">이 지역에 연결된 고등학교의 과외 정보를 확인할 수 있습니다.</p>\n          <ul class="link-list">{links}</ul>\n        </section>\n\n'

def main() -> None:
    rows=json.loads(MANIFEST.read_text(encoding="utf-8"))
    for row in rows:
        path=OUTPUT/row["relative_path"]
        text=path.read_text(encoding="utf-8")
        if MARKER in text: continue
        patched,count=re.subn(r"(\s*</article>)", "\n"+section(row["school_root_slugs"])+r"\1", text, count=1)
        if count != 1: raise RuntimeError(f"patch target missing: {path}")
        path.write_text(patched, encoding="utf-8")
        if patched.count(MARKER) != 1: raise RuntimeError(f"patch count invalid: {path}")
    print(f"Applied {len(rows)} region-school navigation patches")

if __name__ == "__main__": main()
