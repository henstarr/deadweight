"""CLI entry point for deadweight."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="deadweight",
        description="The dead ends registry — approaches your agent should never try again.",
    )
    sub = parser.add_subparsers(dest="command")

    serve_p = sub.add_parser("serve", help="Start the deadweight server")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8340)
    serve_p.add_argument("--reload", action="store_true")

    args = parser.parse_args()

    if args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print("Install uvicorn: pip install 'deadweight[server]'", file=sys.stderr)
            sys.exit(1)
        uvicorn.run(
            "deadweight.server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
