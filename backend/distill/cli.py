"""Command line: `distill import-takeout <path>`, `ingest`, `classify`, `rules`, `eval`, `usage`, `serve`."""
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
    ing = sub.add_parser("ingest", help="fetch new uploads from trusted and mixed channels, then classify")
    ing.add_argument("--no-classify", action="store_true", help="skip the LLM step")
    ing.add_argument("--no-discover", action="store_true", help="skip discovery")
    cls = sub.add_parser("classify", help="classify mixed-channel videos waiting for the LLM")
    cls.add_argument("--limit", type=int, help="classify at most this many")
    cls.add_argument("--no-wait", action="store_true", help="submit a batch and return")
    sub.add_parser("rules", help="re-apply config/rules.yaml (no LLM calls)")
    sub.add_parser("eval", help="check rules + classifications against your overrides")
    sub.add_parser("usage", help="show LLM spend")
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
        llm = None
        if os.getenv("ANTHROPIC_API_KEY") and not args.no_classify:
            import anthropic
            llm = anthropic.Anthropic()
        try:
            with db.session() as conn:
                r = ingest(conn, YouTube(), discover=not args.no_discover, llm=llm)
        except MissingApiKey as e:
            raise SystemExit(f"error: {e}")
        print(f"{r.channels} channels, {r.new_videos} new videos, {r.detailed} detailed, "
              f"{r.short_checks} Shorts checks, {r.visible} visible, {r.errors} errors.")
        if d := r.discovery:
            print(f"Discovery: {d.searches} searches, {d.hn_stories} HN stories, {d.seeds} liked/watched "
                  f"videos mined, {d.llm_channels} suggested channels -> {d.new_videos} new videos "
                  f"from {d.new_channels} new channels, {d.errors} errors.")
        if not args.no_classify:
            if os.getenv("ANTHROPIC_API_KEY"):
                _classify()
            else:
                print("Skipping classification: no ANTHROPIC_API_KEY in .env.")
    elif args.cmd == "classify":
        _classify(limit=args.limit, wait=not args.no_wait)
    elif args.cmd == "rules":
        from distill.ingest import apply_rules
        with db.session() as conn:
            print(f"{apply_rules(conn)} visible.")
    elif args.cmd == "eval":
        from distill.classify import evaluate
        with db.session() as conn:
            r = evaluate(conn)
        if not r["labeled"]:
            print("No labels yet. Use Show anyway / Hide this in the app, then run this again.")
            return
        scored = r["labeled"] - r["unclassified"]
        print(f"{r['agree']}/{scored} agree with your overrides "
              f"({r['unclassified']} labeled videos have no classification).")
        for title, reason in r["wrongly_hidden"]:
            print(f"  hidden, you wanted it: {title}  [{reason}]")
        for title, reason in r["wrongly_shown"]:
            print(f"  shown, you hid it:     {title}  [{reason}]")
    elif args.cmd == "usage":
        from distill.classify import month_spend
        from distill.config import settings
        with db.session() as conn:
            rows = conn.execute("SELECT * FROM llm_usage ORDER BY date DESC LIMIT 14").fetchall()
            spent = month_spend(conn)
        print(f"This month: ${spent:.4f} of ${settings.llm_monthly_budget_usd:.2f}")
        for r in rows:
            print(f"  {r['date']}  {r['requests']:>5} calls  {r['input_tokens']:>8} in  "
                  f"{r['output_tokens']:>7} out  {r['cache_read_tokens']:>8} cached  ${r['cost_usd']:.4f}")
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("distill.api:app", host=args.host, port=args.port, reload=args.reload)


def _classify(limit: int | None = None, wait: bool = True) -> None:
    from distill.classify import classify
    with db.session() as conn:
        r = classify(conn, limit=limit, wait_s=900 if wait else 0)
    print(f"Classified {r.classified}, {r.errors} errors, {r.visible} visible in the feed.")
    if r.pending_batch:
        print(f"{r.pending_batch} videos still in a batch; run `distill classify` later to collect them.")
    if r.skipped_budget:
        print(f"{r.skipped_budget} videos skipped: monthly LLM budget reached (llm_monthly_budget_usd).")


if __name__ == "__main__":
    main()
