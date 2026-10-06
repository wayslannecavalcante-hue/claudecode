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
DETAILS_DIR = ROOT / "data" / "details"
RITUAL_OK = {"SIM"}
RITUAL_GAP = {"NÃO", "NÃO APARECEU"}
RITUAL_MOVED = {"REMARCADA", "REMARCADAA", "MARCADA"}
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

    renewals = [c for c in active if c["group"] == "renovacao" and c["status"] != "renovação fechada"]
    renewed = [c for c in active if c["status"] == "renovação fechada"]

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
            "renovacao": len(renewals),
            "renovadas": len(renewed),
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
        "all_clients": clients,
        "renewals": sorted(renewals, key=lambda c: (c["cs"], c["name"])),
        "new_month": sorted(new_month, key=lambda c: c["name"]),
        "overdue_rows": overdue_rows,
        "retention": snap.get("retention", {}),
        "notes": snap.get("notes", []),
        "news": snap.get("news", []),
        "world": snap.get("world", []),
        "weather": snap.get("weather", {}),
        "skalo": snap.get("skalo", {}),
        "agenda": snap.get("agenda", {}),
        "cobertura": round(100 * (len(active) - len(no_meet)) / max(len(active), 1)),
    }


def load_details(date):
    """Custom fields per client (extract_fields.py output). Uses the newest file up to `date`;
    all files sharing that date prefix (e.g. 2026-10-04.json, 2026-10-04.p1.json) are merged."""
    days = sorted({f.name[:10] for f in DETAILS_DIR.glob("*.json") if f.name[:10] <= date})
    if not days:
        return {}, None
    day = days[-1]
    merged = {}
    for f in sorted(DETAILS_DIR.glob(f"{day}*.json")):
        merged.update(load_json(f))
    return merged, day


STOP_WORDS = {"veiculos", "veiculo", "automoveis", "seminovos", "negocios", "ltda", "01", "2023", "rp", "bm"}


def name_key(n):
    import re
    import unicodedata
    n = unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower()
    toks = [{"multmarcas": "multimarcas"}.get(t, t) for t in re.split(r"[^a-z0-9&]+", n) if t]
    return " ".join(t for t in toks if t not in STOP_WORDS) or " ".join(toks)


def skalo_index(skalo, aliases):
    """Map ClickUp client name keys to Skalo.IA data (ranking, no spend, account errors)."""
    idx = {}
    def put(name, **kv):
        k = name_key(aliases.get(name.strip(), name))
        idx.setdefault(k, {"skalo_nome": name.strip()}).update(kv)
    for n, gasto, res, cpr in skalo.get("ranking", []):
        put(n, gasto=gasto, resultados=res, cpr=cpr)
    for n in skalo.get("sem_gasto", []):
        put(n, gasto=0, resultados=0, cpr=None)
    for n in skalo.get("contas_erro", []):
        put(n, erro_conta=True)
    return idx


def find_skalo(idx, name):
    k = name_key(name)
    if k in idx:
        return idx[k]
    # Fuzzy: same first word when one side is a single word, and only if unambiguous.
    hits = [v for kk, v in idx.items() if kk and k and kk.split()[0] == k.split()[0]
            and (len(k.split()) == 1 or len(kk.split()) == 1)]
    return hits[0] if len(hits) == 1 else None


def brl(v):
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def diretoria(r, snap, details, details_day, cfg):
    """Director + coordination view built from the clients' custom fields."""
    if not details:
        return None
    today = dt.date.fromisoformat(snap["date"])
    now_ms = dt.datetime(today.year, today.month, today.day, 12, tzinfo=dt.timezone(dt.timedelta(hours=-3))).timestamp() * 1000
    days_since = lambda ms: int((now_ms - ms) // 86400000) if ms else None
    churn_ids = set(r["churn_month_ids"])
    sk_idx = skalo_index(r.get("skalo") or {}, cfg.get("skalo_alias", {}))
    rows = []
    for c in r["all_clients"]:
        d = details.get(c["id"])
        if not d:
            continue
        rit = {k.strip(): str(v).strip() for k, v in (d.get("rituais") or {}).items()}
        cs_full = d.get("cs") or ""
        row = {
            "id": c["id"], "name": c["name"], "url": c["url"], "status": c["status"], "group": c["group"],
            "cs": short(cs_full.split(",")[0].strip(), cfg) if cs_full else "Sem CS",
            "gestor": c["cs"], "fee_raw": float(d.get("fee") or 0), "squad": d.get("squad") or "Sem squad",
            "plano": str(d.get("plano") or "").strip(), "contrato": str(d.get("contrato") or "").strip(),
            "dias_reuniao": days_since(d.get("ultima_reuniao")),
            "dias_auditoria": days_since(d.get("ultima_auditoria")),
            "lt_meses": (lambda e: (today.year - e.year) * 12 + today.month - e.month)(
                dt.date.fromtimestamp(d["entrada"] / 1000)) if d.get("entrada") else None,
            "rit_ok": sum(1 for v in rit.values() if v in RITUAL_OK),
            "rit_gap": [k for k, v in rit.items() if v in RITUAL_GAP and not k.startswith("Treinamento")],
            "rit_moved": [k for k, v in rit.items() if v in RITUAL_MOVED],
            "trein_gap": sum(1 for k, v in rit.items() if k.startswith("Treinamento") and v in RITUAL_GAP),
            "churn_mes": c["id"] in churn_ids,
            "missing": [lbl for key, lbl in (("cs", "CS"), ("fee", "fee"), ("squad", "squad"),
                                             ("entrada", "data de entrada"), ("contrato", "contrato"),
                                             ("ultima_reuniao", "última reunião")) if not d.get(key)],
        }
        fee_max = cfg.get("fee_max_plausivel", 50000)
        row["fee"] = row["fee_raw"] if row["fee_raw"] <= fee_max else 0.0
        issues = []
        if row["fee_raw"] > fee_max:
            issues.append((f"fee suspeito ({brl(row['fee_raw'])})", 3))
        if row["contrato"] and row["contrato"] != "ASSINOU":
            issues.append(("contrato " + row["contrato"].lower(), 3))
        if row["dias_reuniao"] is None:
            issues.append(("sem data de reunião", 2))
        elif row["dias_reuniao"] >= 15:
            issues.append((f"{row['dias_reuniao']} dias sem reunião", 3 if row["dias_reuniao"] >= 30 else 2))
        if row["rit_gap"]:
            issues.append(("ritual marcado NÃO: " + ", ".join(x.replace("Checkpoint", "CP").replace("Relatório", "Rel") for x in row["rit_gap"]), len(row["rit_gap"])))
        if row["missing"]:
            issues.append(("falta " + ", ".join(row["missing"]), 1))
        row["issues"] = [i for i, _ in issues]
        row["score"] = sum(w for _, w in issues)
        rows.append(row)

    active = [x for x in rows if x["group"] != "churn"]
    n_active_total = r["kpis"]["ativos"]
    mrr = sum(x["fee"] for x in active)
    em_churn = [x for x in rows if x["group"] == "churn"]
    churn_mes = [x for x in rows if x["churn_mes"]]
    sem_reu = [x for x in active if x["dias_reuniao"] is None or x["dias_reuniao"] >= 15]
    renov = [x for x in active if x["group"] == "renovacao" and x["status"] != "renovação fechada"]
    renovadas = [x for x in active if x["status"] == "renovação fechada"]
    risco_ids = {x["id"] for x in em_churn + churn_mes} | {x["id"] for x in sem_reu if (x["dias_reuniao"] or 99) >= 30}
    risco = [x for x in rows if x["id"] in risco_ids]
    base_mes = mrr + sum(x["fee"] for x in churn_mes if x["group"] == "churn")

    by_squad = defaultdict(lambda: [0, 0.0])
    for x in active:
        by_squad[x["squad"]][0] += 1
        by_squad[x["squad"]][1] += x["fee"]

    per_cs = defaultdict(list)
    for x in rows:
        per_cs[x["cs"]].append(x)
    audit = []
    for cs, xs in per_cs.items():
        act = [x for x in xs if x["group"] != "churn"]
        rit_total = sum(x["rit_ok"] + len(x["rit_gap"]) for x in act)
        audit.append({
            "cs": cs, "ativos": len(act), "mrr": sum(x["fee"] for x in act),
            "em_churn": sum(1 for x in xs if x["group"] == "churn"),
            "mrr_churn": sum(x["fee"] for x in xs if x["group"] == "churn" or x["churn_mes"]),
            "sem_reuniao": sum(1 for x in act if x["dias_reuniao"] is None or x["dias_reuniao"] >= 15),
            "rituais_pct": round(100 * sum(x["rit_ok"] for x in act) / rit_total) if rit_total else None,
            "rituais_gap": sum(len(x["rit_gap"]) for x in act),
            "remarcados": sum(len(x["rit_moved"]) for x in act),
            "contrato_pend": sum(1 for x in act if x["contrato"] and x["contrato"] != "ASSINOU"),
            "sem_auditoria": sum(1 for x in act if x["dias_auditoria"] is None or x["dias_auditoria"] > 30),
            "dados": sum(1 for x in act if x["missing"]),
        })
    audit.sort(key=lambda a: (-a["ativos"], a["cs"]))

    conferir = sorted((x for x in active if x["issues"]), key=lambda x: (-x["score"], -x["fee"]))
    hig = Counter(m for x in active for m in x["missing"])
    return {
        "details_day": details_day,
        "cobertos": len(active), "ativos_total": n_active_total,
        "mrr": mrr, "ticket": mrr / max(len(active), 1),
        "mrr_em_churn": sum(x["fee"] for x in em_churn),
        "mrr_churn_mes": sum(x["fee"] for x in churn_mes),
        "churn_mes_pct": round(100 * sum(x["fee"] for x in churn_mes) / base_mes, 1) if base_mes else 0,
        "mrr_risco": sum(x["fee"] for x in risco), "n_risco": len(risco),
        "mrr_sem_reuniao": sum(x["fee"] for x in sem_reu), "n_sem_reuniao": len(sem_reu),
        "mrr_renov": sum(x["fee"] for x in renov), "n_renov": len(renov),
        "mrr_renovadas": sum(x["fee"] for x in renovadas), "renovadas": [x["name"] for x in renovadas],
        "squads": sorted(({"squad": k, "n": v[0], "mrr": v[1]} for k, v in by_squad.items()), key=lambda s: -s["mrr"]),
        "audit": audit,
        "conferir": [{k: x[k] for k in ("id", "name", "url", "cs", "gestor", "fee", "status", "issues", "score")} for x in conferir],
        "contrato_pend": [{"name": x["name"], "url": x["url"], "cs": x["cs"], "fee": x["fee"], "contrato": x["contrato"]}
                          for x in active if x["contrato"] and x["contrato"] != "ASSINOU"],
        "fee_suspeito": [{"name": x["name"], "url": x["url"], "cs": x["cs"], "fee": x["fee_raw"]}
                         for x in active if x["fee_raw"] > cfg.get("fee_max_plausivel", 50000)],
        "higiene": {"faltando": dict(hig), "sem_auditoria": sum(1 for x in active if x["dias_auditoria"] is None),
                    "auditoria_30d": sum(1 for x in active if x["dias_auditoria"] is not None and x["dias_auditoria"] <= 30),
                    "treinamento_nao": sum(1 for x in active if x["trein_gap"])},
        "clientes": [{"id": x["id"], "name": x["name"], "url": x["url"], "cs": x["cs"], "gestor": x["gestor"],
                      "fee": x["fee"], "status": x["status"], "group": x["group"], "squad": x["squad"],
                      "plano": x["plano"], "contrato": x["contrato"], "dias_reuniao": x["dias_reuniao"],
                      "lt": x["lt_meses"], "rit_ok": x["rit_ok"], "rit_gap": x["rit_gap"], "issues": x["issues"],
                      "score": x["score"], "churn_mes": x["churn_mes"],
                      "skalo": find_skalo(sk_idx, x["name"])}
                     for x in sorted(rows, key=lambda x: x["name"])],
        "maiores": [{"name": x["name"], "url": x["url"], "cs": x["cs"], "fee": x["fee"], "issues": x["issues"]}
                    for x in sorted(active, key=lambda x: -x["fee"])[:10]],
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
    dr = r.get("dir")
    if dr:
        if dr["mrr_risco"]:
            items.append({"sev": "critical", "title": f"{brl(dr['mrr_risco'])} de MRR em risco ({dr['n_risco']} clientes)",
                          "detail": f"Status churn, churn previsto para {r['month']} ou 30+ dias sem reunião. "
                                    f"Churn previsto no mês: {brl(dr['mrr_churn_mes'])} ({str(dr['churn_mes_pct']).replace('.', ',')}% do MRR)."})
        if dr["fee_suspeito"]:
            items.append({"sev": "serious", "title": f"{len(dr['fee_suspeito'])} fee oficial com valor fora do padrão (fora do MRR)",
                          "detail": ", ".join(f"{c['name']}: {brl(c['fee'])} ({c['cs']})" for c in dr["fee_suspeito"]) + ". Corrija no ClickUp."})
        if dr["contrato_pend"]:
            items.append({"sev": "serious", "title": f"{len(dr['contrato_pend'])} clientes ativos sem contrato assinado",
                          "detail": ", ".join(f"{c['name']} ({c['cs']})" for c in dr["contrato_pend"][:6]) + ("…" if len(dr["contrato_pend"]) > 6 else "")})
        if dr["higiene"]["auditoria_30d"] == 0:
            items.append({"sev": "warning", "title": "Nenhum cliente com auditoria da coordenação nos últimos 30 dias",
                          "detail": "O campo \"Última auditoria coord\" está vazio. Ao conferir um cliente, preencha a data para o Jarvis acompanhar."})
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
    ev = [e for e in (r.get("agenda") or {}).get("events") or [] if not e.get("all_day") and e.get("start") and e.get("end")]
    clashes = [f"{a['start']} {a['title'].strip()} × {c['title'].strip()}" for i, a in enumerate(ev) for c in ev[i + 1:]
               if a["start"] < c["end"] and c["start"] < a["end"]]
    if clashes:
        items.append({"sev": "info", "title": f"{len(clashes)} conflitos de horário na sua agenda de hoje",
                      "detail": "; ".join(clashes)})
    rank = {"critical": 0, "serious": 1, "warning": 2, "info": 3}
    return sorted(items, key=lambda i: rank.get(i["sev"], 9))


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
    details, details_day = load_details(cur["date"])
    cur["dir"] = diretoria(cur, load_json(snaps[idx]), details, details_day, cfg)
    cur.pop("all_clients", None)
    if prev:
        prev.pop("all_clients", None)
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
