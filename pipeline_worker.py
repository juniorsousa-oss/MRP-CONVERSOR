from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import pipeline_sync as pipelines


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    summary: list[dict] = []
    failed = False

    print(f"[SETTA PIPELINE WORKER] início {started}")

    for report_type in pipelines.PIPELINES:
        try:
            result = pipelines.sync_pipeline(report_type)
            status = str(result.get("sync_status") or "SEM STATUS").upper()
            state = {
                "pipeline": report_type,
                "status": status,
                "stale_before": bool(result.get("stale")),
                "ready": bool(result.get("ready")),
                "error": str(result.get("error") or ""),
            }
            published = result.get("published") or {}
            if published:
                state["rows_count"] = int(published.get("rows_count") or 0)
                state["processed_at"] = str(published.get("processed_at") or "")
            summary.append(state)

            if status == "ERRO":
                failed = True

            print(
                f"[{report_type}] {status}"
                + (f" · {state['error']}" if state["error"] else "")
            )
        except Exception as exc:
            failed = True
            summary.append(
                {
                    "pipeline": report_type,
                    "status": "ERRO",
                    "ready": False,
                    "stale_before": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[{report_type}] ERRO · {type(exc).__name__}: {exc}")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
