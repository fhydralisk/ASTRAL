"""Run the internal Harness HTTP API independently of the Web application."""

import argparse


def setup_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="astral serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--root", default="./harness-data")
    parser.add_argument("--global-tasks", type=int, default=8)
    parser.add_argument("--per-user-tasks", type=int, default=2)
    return parser


def main(args):
    import uvicorn
    from ..service.local import LocalHarnessService
    from ..http.app import create_app

    service = LocalHarnessService(
        args.root, global_tasks=args.global_tasks, per_user_tasks=args.per_user_tasks
    )
    app = create_app(service)
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)
    return 0
