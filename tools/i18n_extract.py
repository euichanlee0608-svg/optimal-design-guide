#!/usr/bin/env python3
"""index.html에서 번역 대상을 뽑아 i18n/ko.json 으로 저장한다.

두 종류를 뽑는다.
  html : 한글을 품은 '잎 블록' 요소의 innerHTML (인라인 태그를 통째로 보존해야
         문장이 쪼개지지 않는다 — <b> 안에 한글이 356곳 있다)
  js   : <script> 안의 한글 문자열 리터럴. 객체 키로 쓰인 것은 제외한다
         (computed key 로 바꾸면 문법이 깨지므로 빌드 단계에서 따로 처리).
"""
import re, json, sys, os
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 빌드된 index.html 에는 인라인 사전(한글 포함)이 들어 있으므로 반드시 원본에서 뽑는다
_SRCF = os.path.join(ROOT, "index.src.html")
SRC  = _SRCF if os.path.exists(_SRCF) else os.path.join(ROOT, "index.html")
OUT  = os.path.join(ROOT, "i18n", "ko.json")

KO = re.compile(r"[가-힣]")
VOID = {"br","img","input","meta","link","hr","source","use","path","circle","rect","line","polygon","polyline"}
# 이 태그들은 '번역 단위'가 될 수 있다
BLOCK = {"p","li","td","th","h1","h2","h3","h4","h5","h6","summary","figcaption",
         "option","button","a","div","span","small","b","em","strong","label"}
# 통째로 건너뛴다
SKIP = {"script","style","svg","canvas"}


class Collector(HTMLParser):
    """열고 닫힌 위치를 기록해 원본 문자열에서 innerHTML 을 그대로 잘라낸다."""
    def __init__(self, src):
        super().__init__(convert_charrefs=False)
        self.src = src
        self.stack = []          # [(tag, inner_start_offset)]
        self.nodes = []          # [(tag, start, end, depth)]
        self.skip_depth = 0

    def _off(self):
        line, col = self.getpos()
        return self.line_off[line - 1] + col

    def feed_all(self):
        self.line_off = [0]
        for ln in self.src.split("\n"):
            self.line_off.append(self.line_off[-1] + len(ln) + 1)
        self.feed(self.src)

    def handle_starttag(self, tag, attrs):
        if self.skip_depth:
            if tag in SKIP: self.skip_depth += 1
            return
        if tag in SKIP:
            self.skip_depth = 1; return
        if tag in VOID: return
        end = self.src.find(">", self._off()) + 1
        self.stack.append((tag, end))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if self.skip_depth:
            if tag in SKIP: self.skip_depth -= 1
            return
        if tag in VOID: return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                t, s = self.stack[i]
                self.nodes.append((t, s, self._off(), i))
                del self.stack[i:]
                break


def extract_html(src):
    c = Collector(src); c.feed_all()
    # 한글을 품은 노드만
    cand = [n for n in c.nodes if KO.search(src[n[1]:n[2]])]
    cand.sort(key=lambda n: (n[1], -(n[2])))
    # '잎 블록' = 자기 안에 또 다른 후보 블록을 (한글째로) 품지 않는 것
    chosen = []
    for tag, s, e, d in cand:
        if tag not in BLOCK:
            continue
        inner = src[s:e]
        # 자식 중 한글을 품은 BLOCK 태그가 있으면 이건 잎이 아니다
        has_block_child = False
        for t2, s2, e2, d2 in cand:
            if s2 > s and e2 < e and t2 in BLOCK and t2 not in ("b","em","strong","span","small","a"):
                has_block_child = True; break
        if has_block_child:
            continue
        chosen.append({"tag": tag, "start": s, "end": e, "ko": inner})
    # 겹치는 것 제거 (바깥쪽 우선)
    chosen.sort(key=lambda x: (x["start"], -x["end"]))
    out, last_end = [], -1
    for x in chosen:
        if x["start"] < last_end:
            continue
        txt = x["ko"].strip()
        if not txt or not KO.search(txt):
            continue
        # JS 가 내용을 갈아끼우는 요소는 건드리지 않는다 (토글이 상태를 덮어써 깨진다)
        if 'id="' in txt or 'langopt' in txt:
            continue
        # 언어 선택 버튼의 '한국어/English' 는 두 언어에서 그대로 둔다
        if txt in ("한국어",):
            continue
        out.append(x); last_end = x["end"]
    return out


STR = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'')

def extract_js(src):
    """스크립트별로 한글 리터럴을 뽑는다. 객체 키(`{`/`,` 뒤 + `:` 앞)는 제외."""
    res = []
    for m in re.finditer(r"<script>(.*?)</script>", src, re.S):
        base = m.start(1)
        js = m.group(1)
        for sm in STR.finditer(js):
            lit = sm.group(1) if sm.group(1) is not None else sm.group(2)
            if not lit or not KO.search(lit):
                continue
            before = js[max(0, sm.start() - 40):sm.start()]
            after = js[sm.end():sm.end() + 3]
            prev = before.rstrip()
            nxt = after.lstrip()
            is_key = nxt.startswith(":") and (prev.endswith("{") or prev.endswith(","))
            if is_key:
                continue
            res.append({"start": base + sm.start(), "end": base + sm.end(),
                        "quote": '"' if sm.group(1) is not None else "'",
                        "ko": lit})
    return res


def main():
    src = open(SRC, encoding="utf-8").read()
    h = extract_html(src)
    j = extract_js(src)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    data = {
        "html": [{"i": i, "tag": x["tag"], "ko": x["ko"]} for i, x in enumerate(h)],
        "js":   [{"i": i, "ko": x["ko"]} for i, x in enumerate(j)],
    }
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    hc = sum(len(x["ko"]) for x in h); jc = sum(len(x["ko"]) for x in j)
    print(f"html 블록 {len(h):4d}개 ({hc:,}자)")
    print(f"js  문자열 {len(j):4d}개 ({jc:,}자)")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
