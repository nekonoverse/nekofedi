import argparse
import contextlib
import sys

from . import image
from .cli import MisskeyCLI
from .i18n import init_language
from .migrate import run_upgrade


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="misskey-cli",
        description=(
            "Interactive Misskey / Mastodon CLI. Without arguments, starts "
            "an interactive prompt. With -c / -f / piped stdin, runs commands "
            "non-interactively (one per line, '#' for comments)."
        ),
    )
    parser.add_argument(
        "-c",
        "--command",
        action="append",
        default=[],
        metavar="CMD",
        help="Run a single CLI command. Repeatable.",
    )
    parser.add_argument(
        "-f",
        "--file",
        metavar="PATH",
        help="Read commands from a file ('-' for stdin).",
    )
    return parser


def _script_source(args, stack):
    """Return the line iterable for script mode, or ``None`` to stay
    interactive. Any file handle we open is registered on ``stack`` for
    automatic cleanup."""
    if args.command:
        return args.command
    if args.file == "-":
        return sys.stdin
    if args.file:
        return stack.enter_context(open(args.file))
    if not sys.stdin.isatty():
        return sys.stdin
    return None


def main():
    args = _build_parser().parse_args()
    run_upgrade()
    init_language()
    # Probe terminal graphics capability once, before prompt_toolkit takes
    # over stdin/stdout. The result is cached in misskey_cli.image for the
    # rest of the process lifetime.
    image.detect_graphics_backend()
    cli = MisskeyCLI()

    with contextlib.ExitStack() as stack:
        source = _script_source(args, stack)
        if source is not None:
            sys.exit(0 if cli.run_script(source) else 1)

    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
