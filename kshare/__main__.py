import argparse
import json
import sys

from kshare import __version__
from kshare.board import find_board, mirror_board
from kshare.host import serve
from kshare.discover import listen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kshare",
        description="Share this screen on the local network. Watch it with the Windows app.",
    )
    parser.add_argument("--version", action="version", version=f"kshare {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    host = sub.add_parser("host", help="share this computer's screen")
    host.add_argument("--port", type=int, default=47330)
    host.add_argument("--pin", help="6-digit PIN (generated if omitted)")
    host.add_argument("--fps", type=int, default=15)
    host.add_argument("--monitor", help="monitor name (Linux gpu-screen-recorder)")
    host.add_argument("--name", help="name shown to viewers")
    host.add_argument(
        "--no-discover",
        action="store_true",
        help="do not announce this host on the LAN",
    )
    host.add_argument("--status-file", help="write url and PIN as JSON for the Omarchy plugin")

    cast = sub.add_parser("cast", help="mirror to a Horion board, or host for Windows if none is found")
    cast.add_argument("--fps", type=int, default=15)
    cast.add_argument("--monitor", help="monitor name (Linux gpu-screen-recorder)")
    cast.add_argument("--status-file", help="write status JSON for the Omarchy plugin")
    cast.add_argument("--port", type=int, default=47330)
    cast.add_argument("--pin", help="6-digit PIN used when falling back to the Windows host")
    cast.add_argument("--name", help="name shown to Windows viewers")
    cast.add_argument("--no-discover", action="store_true")

    find = sub.add_parser("find", help="list hosts announced on the LAN")
    find.add_argument("--seconds", type=float, default=3.0)

    args = parser.parse_args(argv)
    if args.cmd == "host":
        serve(args)
        return 0
    if args.cmd == "cast":
        board = find_board()
        if board:
            ip, name = board
            try:
                mirror_board(ip, name, args.fps, args.monitor, args.status_file)
            except (OSError, ConnectionError, json.JSONDecodeError) as exc:
                print(f"Board mirror failed: {exc}", flush=True)
                return 1
            return 0
        print("No Horion board found. Starting the Windows host instead.", flush=True)
        serve(args)
        return 0
    if args.cmd == "find":
        hosts = listen(args.seconds)
        if not hosts:
            print("No KShare hosts found.")
            return 1
        for item in hosts:
            print(f"{item['name']}\t{item['url']}\tpin required")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
