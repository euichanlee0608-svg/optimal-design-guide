#!/usr/bin/env python3
"""index.html 에 KO/EN 토글을 주입한다.

- html 블록: data-i="n" 을 붙이고, 원문/번역을 I18N.h[n] 에 넣어 innerHTML 을 교체
- js 리터럴: __T("...") 로 감싸 런타임에 사전을 타게 한다 (T 는 moo 지역변수와 충돌)
- <title>/meta/description 은 별도 항목으로 교체
- 결과는 self-contained (사전이 index.html 안에 인라인됨)

입력  : i18n/ko.json (추출본) · i18n/en.json (번역, {"html":{n:...},"js":{n:...},"meta":{...}})
대상  : index.src.html 이 있으면 그것을, 없으면 index.html 을 원본으로 삼아
        index.src.html 로 보존한 뒤 index.html 을 생성한다 (재실행 안전).
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRCF = os.path.join(ROOT, "index.src.html")
OUTF = os.path.join(ROOT, "index.html")
KOF  = os.path.join(ROOT, "i18n", "ko.json")
ENF  = os.path.join(ROOT, "i18n", "en.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from i18n_extract import extract_html, extract_js  # noqa


def main():
    if os.path.exists(SRCF):
        src = open(SRCF, encoding="utf-8").read()
    else:
        src = open(OUTF, encoding="utf-8").read()
        open(SRCF, "w", encoding="utf-8").write(src)
        print("원본을 index.src.html 로 보존했습니다")

    en = json.load(open(ENF, encoding="utf-8")) if os.path.exists(ENF) else {}
    en_html = {int(k): v for k, v in en.get("html", {}).items()}
    en_js   = {int(k): v for k, v in en.get("js", {}).items()}
    en_meta = en.get("meta", {})

    H = extract_html(src)
    J = extract_js(src)

    # ── 뒤에서부터 치환해야 오프셋이 밀리지 않는다 ──
    edits = []
    for i, x in enumerate(H):
        # 여는 태그 끝(=inner 시작) 바로 앞에 data-i 를 끼워 넣는다
        open_end = x["start"] - 1           # '>' 위치
        edits.append(("attr", open_end, open_end, f' data-i="{i}"'))
    for i, x in enumerate(J):
        q = x["quote"]
        edits.append(("js", x["start"], x["end"], f'__T({q}{x["ko"]}{q})'))

    edits.sort(key=lambda e: e[1], reverse=True)
    out = src
    for kind, s, e, rep in edits:
        out = out[:s] + rep + out[e:]

    # 사전 키는 '소스 표기'가 아니라 '런타임 문자열 값'이어야 한다.
    # \" 같은 이스케이프가 든 리터럴은 풀어 주지 않으면 __T() 조회가 빗나간다.
    def unescape(lit):
        out, i = [], 0
        table = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f",
                 "\\": "\\", '"': '"', "'": "'", "/": "/", "0": "\0"}
        while i < len(lit):
            c = lit[i]
            if c == "\\" and i + 1 < len(lit):
                nx = lit[i + 1]
                if nx == "u" and i + 5 < len(lit) + 1:
                    try:
                        out.append(chr(int(lit[i + 2:i + 6], 16))); i += 6; continue
                    except ValueError:
                        pass
                out.append(table.get(nx, nx)); i += 2; continue
            out.append(c); i += 1
        return "".join(out)

    ko_html = [x["ko"] for x in H]
    # 빈 문자열도 정당한 번역이다 ("개" → "") — truthiness 로 거르면 안 된다
    dict_js = {
        "h": {str(i): en_html[i] for i in range(len(H)) if en_html.get(i) is not None},
        "s": {unescape(J[i]["ko"]): en_js[i] for i in range(len(J)) if en_js.get(i) is not None},
        "m": en_meta,
    }

    runtime = """
<script>
/* ================= KO / EN ================= */
window.I18N = __DICT__;
window.KO_HTML = __KOHTML__;
(function(){
  const q = new URLSearchParams(location.search).get("lang");
  const saved = (()=>{try{return localStorage.getItem("odg_lang");}catch(e){return null;}})();
  const auto = (navigator.language||"").toLowerCase().startsWith("ko") ? "ko" : "en";
  window.LANG = (q==="en"||q==="ko") ? q : (saved || auto);
})();
function __T(s){
  /* 빈 문자열("개" → "")도 정당한 번역이므로 truthiness 로 판단하면 안 된다 */
  if (window.LANG !== "en" || !I18N.s) return s;
  const v = I18N.s[s];
  return (typeof v === "string") ? v : s;
}
function applyLang(){
  const en = window.LANG === "en";
  document.documentElement.lang = en ? "en" : "ko";
  document.querySelectorAll("[data-i]").forEach(el=>{
    const i = el.getAttribute("data-i");
    const t = en ? (I18N.h && I18N.h[i]) : KO_HTML[i];
    if (typeof t === "string") el.innerHTML = t;
  });
  const m = I18N.m || {};
  if (en) {
    if (m.title) document.title = m.title;
    const d = document.querySelector('meta[name="description"]');
    if (d && m.desc) d.setAttribute("content", m.desc);
  }
  const tl = document.getElementById("toolLabel");
  if (tl) tl.textContent = en ? (m.toolLabel || "Tool labels") : "툴 표기";
  const b = document.getElementById("langBtn");
  if (b) b.textContent = en ? "한국어" : "English";
  document.querySelectorAll(".langopt").forEach(o=>
    o.classList.toggle("on", o.dataset.l === window.LANG));
}
function setLang(l){
  window.LANG = l;
  try{ localStorage.setItem("odg_lang", l); }catch(e){}
  applyLang();
  /* 캔버스는 다시 그려야 라벨이 바뀐다 */
  if (window.ALL_DEMOS) ALL_DEMOS.forEach(d=>{ try{ d.render(); }catch(e){} });
  if (typeof CURRENT !== "undefined" && typeof SEC !== "undefined") {
    const h = SEC[CURRENT];
    if (h && h.onShow) { try{ h.onShow(); }catch(e){} }
  }
  if (typeof markScrollTables === "function") setTimeout(markScrollTables, 60);
}
</script>
"""
    dict_json = json.dumps(dict_js, ensure_ascii=False, separators=(",", ":"))
    koh_json = json.dumps(ko_html, ensure_ascii=False, separators=(",", ":"))
    runtime = runtime.replace("__DICT__", dict_json).replace("__KOHTML__", koh_json)

    # 사이드바의 '툴 표기' 라벨에 id 를 붙인다.
    # 원본을 고치면 추출 인덱스가 밀려 사전이 통째로 어긋나므로, 빌드 단계에서만 감싼다.
    out = out.replace("</div>\n    툴 표기",
                      '</div>\n    <span id="toolLabel">툴 표기</span>', 1)

    # 첫 <script> 앞에 런타임을 넣어 __T() 가 먼저 정의되게 한다
    k = out.find("<script>")
    out = out[:k] + runtime.strip() + "\n" + out[k:]

    # 부팅 마지막에 applyLang 적용
    out = out.replace('buildNav();\ninitMobileShell();\nswitchTab("intro");',
                      'buildNav();\ninitMobileShell();\napplyLang();\nswitchTab("intro");', 1)

    open(OUTF, "w", encoding="utf-8").write(out)
    print(f"html 블록 {len(H)}개 · js 리터럴 {len(J)}개 주입")
    print(f"번역 채워진 것: html {len(dict_js['h'])}/{len(H)} · js {len(dict_js['s'])}/{len(J)}")


if __name__ == "__main__":
    main()
