"""Read-only Superfond ranking digest; no orders or invented news."""
from collections import defaultdict
from datetime import datetime
from math import isfinite

def create_digest(rows, *, at, news=None):
    groups=defaultdict(list)
    all_rows=[]
    seen=set()
    for r in sorted(rows,key=lambda x:(-float(x.get("score") or -1e12),str(x.get("id")))):
        score=r.get("score")
        if score is None or not isfinite(float(score)) or r.get("blocks"):
            continue
        uid=r.get("isin") or r.get("id")
        if not uid or uid in seen: continue
        seen.add(uid)
        item={"name":str(r.get("name") or uid),"id":str(r.get("id") or uid),
              "score":round(float(score),3),"category":str(r.get("category") or "Ukjent"),
              "currency":str(r.get("returns_currency") or "Ukjent"),
              "price_at":str(r.get("price_at") or ""),
              "returns":{k:(r.get("returns") or {}).get(k) for k in ("yield_1w","yield_1m","yield_3m")}}
        groups[(item["category"],item["currency"])].append(item)
        all_rows.append(item)
    return {"at":at,"qualified_count":len(all_rows),
            "groups":{f"{k[0]} ({k[1]})":v[:5] for k,v in sorted(groups.items())},
            "overall":all_rows[:10],
            "news_status":"Nyheter ikke verifisert eller ikke koblet til enkeltfond",
            "score_note":"60 % uke + 25 % måned + 15 % kvartal; poeng er ikke av 10 eller 100, og ulike avkastningsvalutaer er ikke direkte sammenlignbare."}

def pages(digest, max_chars=900):
    at=digest["at"]
    lines=[f"SUPERFOND – samlet rangeringsrapport {at[:10]}",f"Kvalifiserte instrumenter: {digest.get('qualified_count',0)} · Kategori-/valutagrupper: {len(digest.get('groups',{}))}","","SAMLET TOPP 10 (ulike avkastningsvalutaer)"]
    for i,r in enumerate(digest["overall"],1):
        lines.append(f'{i}. {r["name"]} · score {r["score"]:.2f} ({r["currency"]})')
    lines += ["","TOPP 5 PER BRANSJE/KATEGORI OG VALUTA"]
    for group,rows in digest["groups"].items():
        lines.extend(["", group])
        for i,r in enumerate(rows,1):
            ret=r["returns"]
            def val(key):
                x=ret.get(key)
                return f"{float(x):+.1f}%" if x is not None else "ukjent"
            lines.append(f'{i}. {r["name"]} · score {r["score"]:.2f} ({r["currency"]})')
            lines.append(f'   Uke {val("yield_1w")} · Måned {val("yield_1m")} · 3 mnd {val("yield_3m")}')
    lines.extend(["","FORKLARING","Rangeringen er basert på publisert 1u/1m/3m-avkastning, ikke nyhetsantakelser.",
                  digest["news_status"],digest["score_note"]])
    chunks=[];current=""
    for line in lines:
        if len(current)+len(line)+1>max_chars and current:
            chunks.append(current);current=""
        current+=line+"\n"
    if current:chunks.append(current)
    return chunks
