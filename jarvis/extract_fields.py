#!/usr/bin/env python3
"""Extrai os campos personalizados dos clientes a partir das respostas salvas do ClickUp.

Cada `clickup_get_task` com include=["custom_fields"] devolve ~60 mil caracteres, então
o Claude Code salva a resposta num arquivo em ~/.claude/projects/**/tool-results/.
Este script lê esses arquivos (ou os caminhos passados) e grava um resumo compacto:

    python3 jarvis/extract_fields.py 2026-10-04            # varre tool-results
    python3 jarvis/extract_fields.py 2026-10-04 a.txt b.txt

Saída: jarvis/data/details/<data>.json  ->  {task_id: {campo: valor, ...}}
"""
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RITUALS = [f"{k} {i}" for k in ("Checkpoint", "Relatório", "Treinamento") for i in range(1, 5)]
WANTED = {
    "FEE OFICIAL": "fee", "PLANO": "plano", "SQUAD": "squad", "CS responsável": "cs",
    "📅 DATA DE ENTRADA": "entrada", "Última reunião": "ultima_reuniao",
    "ÚLTIMA AUDITORIA COORD": "ultima_auditoria", "CONTRATO ASSINADO ": "contrato",
    "ACOMPANHAMENTO": "acompanhamento", "TRÁFEGO PAGO": "trafego", "NICHO": "nicho",
    "CALL 3° MÊS": "call_3m", "LANDING PAGE": "landing", "SKALO.IA": "skalo",
    "FORMA DE PAGAMENTO": "pagamento",
}


def option_name(field, value):
    opts = (field.get("type_config") or {}).get("options") or []
    for o in opts:
        if o.get("id") == value or o.get("orderindex") == value:
            return o.get("name") or o.get("label")
    return value


def parse(path):
    raw = open(path, encoding="utf-8").read()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(d, list):
        d = d[0]
    if isinstance(d, dict) and isinstance(d.get("text"), str):
        try:
            d = json.loads(d["text"])
        except json.JSONDecodeError:
            return None
    if not isinstance(d, dict) or "custom_fields" not in d or "id" not in d:
        return None
    if (d.get("list") or {}).get("id") != "901408581641":
        return None
    out = {"name": d.get("name", "").strip(), "status": d.get("status"),
           "assignee": ((d.get("assignees") or [{}])[0] or {}).get("username", ""),
           "date_created": d.get("date_created")}
    rituals = {}
    for f in d["custom_fields"]:
        name, v, t = f.get("name"), f.get("value"), f.get("type")
        if v in (None, "", [], {}):
            continue
        if t == "drop_down":
            v = option_name(f, v)
        elif t == "users":
            v = ", ".join(u.get("username", "") for u in v if isinstance(u, dict))
        elif t == "currency":
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
        elif t == "date":
            try:
                v = int(v)
            except (TypeError, ValueError):
                continue
        if name in RITUALS and t == "drop_down":
            rituals[name] = v
        elif name in WANTED:
            out[WANTED[name]] = v
    out["rituais"] = rituals
    return d["id"], out


def main():
    date = sys.argv[1]
    paths = sys.argv[2:] or glob.glob(os.path.expanduser("~/.claude/projects/**/tool-results/mcp-ClickUp-clickup_get_task-*.txt"), recursive=True)
    target = ROOT / "data" / "details" / f"{date}.json"
    details = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    n = 0
    for p in sorted(paths, key=os.path.getmtime):
        r = parse(p)
        if r:
            details[r[0]] = r[1]
            n += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n} arquivos lidos, {len(details)} clientes em {target}")


if __name__ == "__main__":
    main()
