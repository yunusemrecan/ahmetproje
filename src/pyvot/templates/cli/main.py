"""{{name}}: {{t:cli_doc}}"""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="{{package}}", description="{{t:cli_desc}}")
    parser.add_argument("name", nargs="?", default="{{t:cli_default_name}}", help="{{t:cli_name_help}}")
    parser.add_argument("-n", "--times", type=int, default=1, help="{{t:cli_times_help}}")
    parser.add_argument("--upper", action="store_true", help="{{t:cli_upper_help}}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    message = "{{t:cli_greeting}}".format(name=args.name)
    if args.upper:
        message = message.upper()
    for _ in range(args.times):
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
