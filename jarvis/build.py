#!/usr/bin/env python3
"""Jarvis AEG: turns the daily ClickUp snapshot into the morning dashboard.

Usage:
    python3 jarvis/build.py                 # uses the latest snapshot
    python3 jarvis/build.py 2026-10-03      # uses a specific snapshot

Reads  jarvis/data/snapshots/<date>.json (format documented in JARVIS.md)
Writes jarvis/out/jarvis.html (the page published as the "Jarvis AEG" artifact)
"""
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAP_DIR = ROOT / "data" / "snapshots"
OUT = ROOT / "out" / "jarvis.html"
TEMPLATE = ROOT / "template.html"

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def month_tag_matches(tag, prefix, month_idx, year):
    """'churn outubro/26', 'churn setembro/2026', 'onboarding abril' -> month match."""
    tag = tag.strip().lower()
    if not tag.startswith(prefix + " "):
        return False
    rest = tag[len(prefix) + 1:]
    name, _, yr = rest.partition("/")
    if name.strip() != MESES[month_idx]:
        return False
    yr = yr.strip()
    return yr in ("", str(year), str(year)[2:])


def stage_group(status, cfg):
    for g in cfg["stage_groups"]:
        if any(status.startswith(p) for p in g["prefixes"]):
            return g["key"]
    return "outros"


def short(name, cfg):
    return cfg["people"].get(name, name.split(" ")[0] if name else "Sem responsável")


def task_url(task_id):
    return f"https://app.clickup.com/t/{task_id}"


def metrics(snap, cfg):
    today = dt.date.fromisoformat(snap["date"])
    m_idx, year = today.month - 1, today.year
    prev_m_idx = (m_idx - 1) % 12
    prev_year = year if m_idx > 0 else year - 1

    clients = []
    for cid, name, status, cs, tags in snap["clients"]:
        if any(name.upper().startswith(p) for p in cfg["ignore_name_prefixes"]):
            continue
        tag_list = [t.strip() for t in tags.split("|") if t.strip()]
        clients.append({
            "id": cid, "name": name.strip(), "status": status, "cs": short(cs, cfg),
            "tags": tag_list, "url": task_url(cid),
            "group": "churn" if status == cfg["churn_status"] else stage_group(status, cfg),
        })

    active = [c for c in clients if c["group"] != "churn"]
    in_churn = [c for c in clients if c["group"] == "churn"]
    no_meet_ids = set(snap.get("no_meeting_15d", []))
    no_meet = [c for c in active if c["id"] in no_meet_ids]

    def has_month_tag(c, prefix, mi, yr):
        return any(month_tag_matches(t, prefix, mi, yr) for t in c["tags"])

    churn_month = [c for c in clients if has_month_tag(c, "churn", m_idx, year)]
    churn_prev_month = [c for c in clients if has_month_tag(c, "churn", prev_m_idx, prev_year)]
    new_month = [c for c in clients if has_month_tag(c, "onboarding", m_idx, year)]
    new_prev_month = [c for c in clients if has_month_tag(c, "onboarding", prev_m_idx, prev_year)]

    groups = Counter(c["group"] for c in active)
    statuses = Counter(c["status"] for c in active)
    status_rows = [{"status": s, "n": statuses.get(s, 0), "group": stage_group(s, cfg)}
                   for s in cfg["status_order"] if statuses.get(s, 0)]

    renewals = [c for c in active if c["group"] == "renovacao"]

    # Overdue tasks
    overdue = snap.get("overdue", [])
    od_by = Counter(short(w, cfg) for w, _, _ in overdue)
    od_urgent = Counter(short(w, cfg) for w, _, u in overdue if u)
    od_oldest = {}
    for w, due, _ in overdue:
        k = short(w, cfg)
        od_oldest[k] = min(od_oldest.get(k, due), due)
    overdue_rows = [{"who": k, "n": n, "urgent": od_urgent.get(k, 0),
                     "oldest": od_oldest[k],
                     "days": (today - dt.date.fromisoformat(od_oldest[k])).days}
                    for k, n in od_by.most_common()]

    # Per-CS book
    per_cs = defaultdict(lambda: Counter())
    for c in clients:
        per_cs[c["cs"]][c["group"]] += 1
    for c in no_meet:
        per_cs[c["cs"]]["sem_reuniao"] += 1
    cs_rows = []
    for cs, cnt in per_cs.items():
        ativos = sum(cnt[g] for g in ("onboarding", "maturacao", "ongoing", "renovacao", "outros"))
        if ativos == 0 and cnt["churn"] == 0:
            continue
        cs_rows.append({
            "cs": cs, "ativos": ativos, "onboarding": cnt["onboarding"],
            "maturacao": cnt["maturacao"], "ongoing": cnt["ongoing"],
            "renovacao": cnt["renovacao"], "churn": cnt["churn"],
            "sem_reuniao": cnt["sem_reuniao"], "atrasadas": od_by.get(cs, 0),
        })
    cs_rows.sort(key=lambda r: (-r["ativos"], r["cs"]))

    tag_count = lambda tag: sum(1 for c in active if tag in c["tags"])

    return {
        "date": snap["date"],
        "date_long": f"{DIAS[today.weekday()]}, {today.day} de {MESES[m_idx]} de {year}",
        "month": MESES[m_idx], "prev_month": MESES[prev_m_idx],
        "source": snap.get("source", "ClickUp"),
        "kpis": {
            "ativos": len(active),
            "onboarding": groups.get("onboarding", 0),
            "maturacao": groups.get("maturacao", 0),
            "ongoing": groups.get("ongoing", 0),
            "renovacao": groups.get("renovacao", 0),
            "em_churn": len(in_churn),
            "churn_mes": len(churn_month),
            "churn_mes_anterior": len(churn_prev_month),
            "novos_mes": len(new_month),
            "novos_mes_anterior": len(new_prev_month),
            "sem_reuniao": len(no_meet),
            "atrasadas": len(overdue),
            "atrasadas_truncado": bool(snap.get("overdue_truncated")),
            "mrr": tag_count("mrr"), "arr": tag_count("arr"),
            "venda_ia": tag_count("venda.ia"), "crm_ia": tag_count("crm.ia"),
        },
        "groups": [{"key": g["key"], "label": g["label"], "n": groups.get(g["key"], 0)}
                   for g in cfg["stage_groups"]],
        "status_rows": status_rows,
        "cs_rows": cs_rows,
        "in_churn": sorted(in_churn, key=lambda c: (c not in churn_month, c["cs"], c["name"])),
        "churn_month_ids": [c["id"] for c in churn_month],
        "no_meeting": sorted(no_meet, key=lambda c: (c["cs"], c["name"])),
        "renewals": sorted(renewals, key=lambda c: (c["cs"], c["name"])),
        "new_month": sorted(new_month, key=lambda c: c["name"]),
        "overdue_rows": overdue_rows,
        "retention": snap.get("retention", {}),
        "notes": snap.get("notes", []),
    }


def deltas(cur, prev):
    if not prev:
        return {}
    out = {}
    for k in ("ativos", "onboarding", "em_churn", "churn_mes", "sem_reuniao", "atrasadas", "novos_mes"):
        out[k] = cur["kpis"][k] - prev["kpis"][k]
    return {"vs": prev["date"], "kpis": out}


def priorities(r, cfg):
    """Ranked list of what deserves attention this morning."""
    k = r["kpis"]
    items = []
    cm = [c for c in r["in_churn"] if c["id"] in r["churn_month_ids"]]
    if cm:
        items.append({"sev": "critical", "title": f"{len(cm)} clientes com churn previsto para {r['month']}",
                      "detail": ", ".join(f"{c['name']} ({c['cs']})" for c in cm[:8]) + ("…" if len(cm) > 8 else "")})
    if k["em_churn"]:
        items.append({"sev": "serious", "title": f"{k['em_churn']} clientes no status churn aguardando tratativa",
                      "detail": "Confirme quem ainda dá para reverter e quem precisa ir para \"cancelou\"."})
    if k["sem_reuniao"]:
        by = Counter(c["cs"] for c in r["no_meeting"]).most_common(3)
        items.append({"sev": "serious", "title": f"{k['sem_reuniao']} clientes ativos sem reunião há 15+ dias",
                      "detail": "Mais concentrados em: " + ", ".join(f"{cs} ({n})" for cs, n in by)})
    heavy = [o for o in r["overdue_rows"] if o["n"] >= cfg["overdue_alert_per_person"]]
    if k["atrasadas"]:
        tot = f"{k['atrasadas']}+" if k["atrasadas_truncado"] else str(k["atrasadas"])
        items.append({"sev": "warning", "title": f"{tot} tarefas atrasadas nos squads e obrigações",
                      "detail": ("Acima de %d por pessoa: " % cfg["overdue_alert_per_person"]) +
                      ", ".join(f"{o['who']} ({o['n']})" for o in heavy) if heavy else "Distribuição equilibrada."})
    if r["renewals"]:
        items.append({"sev": "warning", "title": f"{len(r['renewals'])} renovações em aberto",
                      "detail": "Nenhuma com proposta registrada. Mova para \"renovação proposta feita\" ao enviar."
                      if not any(c["status"] == "renovação proposta feita" for c in r["renewals"]) else ""})
    ret = r.get("retention") or {}
    closed = ret.get("closed_total", {})
    opn = sum(ret.get("open", {}).values())
    if ret and opn and sum(closed.values()) == 0:
        items.append({"sev": "info", "title": "CRM Retenção sem nenhum card fechado",
                      "detail": f"{opn}{'+' if ret.get('open_truncated') else ''} cards abertos e nenhum marcado como retido ou perdido."})
    for n in r.get("notes", []):
        items.append({"sev": "info", "title": n, "detail": ""})
    return items


def main():
    cfg = load_json(ROOT / "config.json")
    snaps = sorted(SNAP_DIR.glob("*.json"))
    if not snaps:
        sys.exit("Nenhum snapshot em jarvis/data/snapshots/")
    if len(sys.argv) > 1:
        target = SNAP_DIR / f"{sys.argv[1]}.json"
        idx = snaps.index(target)
    else:
        idx = len(snaps) - 1
    cur = metrics(load_json(snaps[idx]), cfg)
    prev = metrics(load_json(snaps[idx - 1]), cfg) if idx > 0 else None
    cur["delta"] = deltas(cur, prev)
    cur["priorities"] = priorities(cur, cfg)
    cur["history"] = [{"date": p.stem, **{k: v for k, v in metrics(load_json(p), cfg)["kpis"].items()
                                          if k in ("ativos", "em_churn", "sem_reuniao", "atrasadas")}}
                      for p in snaps[max(0, idx - 29): idx + 1]]
    cur["generated_at"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%d/%m %H:%M")

    html = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(cur, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("/*__JARVIS_DATA__*/null", payload)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    k = cur["kpis"]
    print(f"OK {cur['date']}: {k['ativos']} ativos, {k['em_churn']} em churn, "
          f"{k['sem_reuniao']} sem reunião, {k['atrasadas']} atrasadas -> {OUT}")


if __name__ == "__main__":
    main()
