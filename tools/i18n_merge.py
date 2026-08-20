#!/usr/bin/env python3
"""번역 배치를 i18n/en.json 에 병합한다 (기존 값 보존, 배치마다 즉시 저장).

사용: python3 tools/i18n_merge.py html < batch.json
      python3 tools/i18n_merge.py js   < batch.json
batch.json = {"12":"English text", "13":"..."}
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENF = os.path.join(ROOT, "i18n", "en.json")


def load():
    if os.path.exists(ENF):
        return json.load(open(ENF, encoding="utf-8"))
    return {"html": {}, "js": {}, "meta": {}}


def main():
    kind = sys.argv[1]
    batch = json.load(sys.stdin)
    en = load()
    en.setdefault(kind, {})
    en[kind].update(batch)
    json.dump(en, open(ENF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ko = json.load(open(os.path.join(ROOT, "i18n", "ko.json"), encoding="utf-8"))
    for k in ("html", "js"):
        print(f"  {k}: {len(en.get(k,{}))}/{len(ko[k])}")


if __name__ == "__main__":
    main()
