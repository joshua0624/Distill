"""Command line: `distill import-takeout <path>`, `distill ingest`, `distill serve`."""
import argparse
import logging
import os
from pathlib import Path

from distill import db
from distill.youtube import MissingApiKey, YouTube


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="distill")
    sub = p.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import-takeout", help="import a Google Takeout folder or zip contents")
    imp.add_argument("path", type=Path)
    sub.add_parser("ingest", help="fetch new uploads from trusted and mixed channels")
    srv = sub.add_parser("serve", help="run the API (and built frontend)")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    srv.add_argument("--reload", action="store_true")
    args = p.parse_args()

    if args.cmd == "import-takeout":
        from distill.takeout import import_takeout
        with db.session() as conn:
            r = import_takeout(conn, args.path.expanduser())
        print(f"Imported {r.watches} watches ({r.skipped} skipped: ads, Music, removed), "
              f"{r.subscriptions} subscriptions. {r.channels} channels to triage.")
    elif args.cmd == "ingest":
        from distill.ingest import ingest
        try:
            with db.session() as conn:
                r = ingest(conn, YouTube())
        except MissingApiKey as e:
            raise SystemExit(f"error: {e}")
        print(f"{r.channels} channels, {r.new_videos} new videos, {r.detailed} detailed, "
              f"{r.short_checks} Shorts checks, {r.visible} visible, {r.errors} errors.")
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("distill.api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
