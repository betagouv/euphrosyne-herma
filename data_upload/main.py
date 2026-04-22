import argparse
import logging
import sys

logger = logging.getLogger(__name__)


CLI_UPLOAD_ARGS = {"--project", "--run", "--data-type", "--data-path", "--email"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="""Link data to a Euphrosyne run & upload data to Azure Fileshare.
        If upload arguments are provided, CLI mode will be used, otherwise it will launch the GUI app."""
    )
    parser.add_argument("--log", default="INFO", help="Log level (default: INFO)")
    return parser


def _is_cli_mode(argv: list[str]) -> bool:
    return any(arg in CLI_UPLOAD_ARGS for arg in argv)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if _is_cli_mode(argv):
        from data_upload.cli import main as cli_main

        return cli_main(argv)

    parser = build_parser()
    args = parser.parse_args(argv)
    numeric_level = getattr(logging, args.log.upper(), None)
    if not isinstance(numeric_level, int):
        parser.error(f"Invalid log level: {args.log}")
    logging.basicConfig(level=numeric_level)

    from data_upload.gui import ConverterGUI

    logger.debug("GUI mode")
    ConverterGUI.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
