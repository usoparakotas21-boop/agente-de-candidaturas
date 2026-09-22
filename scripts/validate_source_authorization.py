"""Validate one source-authorization JSON record without enabling it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.source_authorization import check_source, load_source_record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", help="path to a completed authorization JSON record")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="print machine-readable output"
    )
    args = parser.parse_args()

    try:
        source = load_source_record(args.record)
        result = check_source(source)
    except ValueError as exc:
        payload = {
            "schema_valid": False,
            "ready_for_registration": False,
            "errors": [str(exc)],
        }
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"Inválido: {exc}", file=sys.stderr)
        return 2

    payload = result.as_dict()
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        state = (
            "pronto para revisão final"
            if result.ready_for_registration
            else "bloqueado até completar a autorização"
        )
        print(f"Fonte: {result.source_id}\nEstado: {state}")
        if result.approval_gaps:
            print("Campos ausentes: " + ", ".join(result.approval_gaps))
        if result.approval_error:
            print("Motivo: " + result.approval_error)
        print("Nenhuma fonte foi registrada ou ativada por este comando.")
    return 0 if result.ready_for_registration else 3


if __name__ == "__main__":
    raise SystemExit(main())
