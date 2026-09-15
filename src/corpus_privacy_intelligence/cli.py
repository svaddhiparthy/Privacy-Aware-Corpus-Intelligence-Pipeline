from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import run_pipeline
from .reports import write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify a large text export into public candidates and private exclusions."
    )
    parser.add_argument("--export-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--min-public-score", type=float, default=55.0)
    parser.add_argument("--chunk-chars", type=int, default=9000)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_pipeline(
        export_dir=args.export_dir,
        min_public_score=args.min_public_score,
        chunk_chars=args.chunk_chars,
    )
    summary = result["summary"]
    summary.update(
        {
            "export_dir": str(args.export_dir),
            "out_dir": str(args.out_dir),
            "min_public_score": args.min_public_score,
            "chunk_chars": args.chunk_chars,
        }
    )
    write_outputs(
        out_dir=args.out_dir,
        public_rows=result["public"],
        excluded_rows=result["excluded"],
        skipped_rows=result["skipped"],
        summary=summary,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
