"""Command-line interface for reproducible and scriptable audits."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from .audit import build_audit_report
from .clients import (
    ArcticShiftClient,
    ConfigurationError,
    DataSourceError,
    RedditCredentials,
    RedditPublicClient,
)
from .demo import demo_report
from .exports import report_to_csv, report_to_json
from .parsing import ProfileInputError, extract_username


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="profilelens",
        description="Audit what a Reddit profile lists versus what an archive recorded.",
    )
    parser.add_argument("profile", nargs="?", help="Reddit profile URL or username")
    parser.add_argument("--limit", type=int, default=100, help="Comments per source (default: 100)")
    parser.add_argument(
        "--compare-live",
        action="store_true",
        help="Use approved Reddit Data API credentials for a live comparison",
    )
    parser.add_argument(
        "--max-probes",
        type=int,
        default=20,
        help="Maximum direct comment lookups (default: 20)",
    )
    parser.add_argument(
        "--demo", action="store_true", help="Generate a fictional demonstration report"
    )
    parser.add_argument(
        "--include-body", action="store_true", help="Include full comment text in exports"
    )
    parser.add_argument("--output", type=Path, default=Path("profilelens-audit.json"))
    parser.add_argument(
        "--acknowledge-authorized-use",
        action="store_true",
        help="Confirm that you own or have permission to audit the account",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)

    try:
        if args.demo:
            report = demo_report()
        else:
            if not args.profile:
                raise ProfileInputError("Provide a Reddit profile URL or username, or use --demo.")
            if not args.acknowledge_authorized_use:
                raise ProfileInputError(
                    "Add --acknowledge-authorized-use to confirm account ownership or permission."
                )
            username = extract_username(args.profile)
            archived = ArcticShiftClient().get_user_comments(username, limit=args.limit)
            public = []
            reddit_client = None
            if args.compare_live:
                credentials = RedditCredentials.from_environment()
                if credentials is None:
                    raise ConfigurationError(
                        "Approved Reddit API access is not configured; see .env.example."
                    )
                reddit_client = RedditPublicClient(credentials)
                public = reddit_client.get_profile_comments(username, limit=args.limit)
            report = build_audit_report(
                username,
                archived,
                public,
                public_profile_compared=args.compare_live,
                requested_public_limit=args.limit,
                probe=reddit_client.probe_comment if reddit_client else None,
                max_probes=args.max_probes,
            )
    except (ConfigurationError, DataSourceError, ProfileInputError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".csv":
        output.write_bytes(report_to_csv(report, include_body=args.include_body))
    else:
        if output.suffix.lower() != ".json":
            output = output.with_suffix(".json")
        output.write_bytes(report_to_json(report, include_body=args.include_body))

    print(f"Audit complete for u/{report.username}: {len(report.rows)} result rows")
    for status, count in report.summary.items():
        print(f"  {count:>3}  {status}")
    print(f"Saved: {output.resolve()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
