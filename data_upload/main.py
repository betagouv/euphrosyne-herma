import argparse
import logging
import pathlib

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""Link data to a Euphrosyne run & upload data to Azure Fileshare.
        If -e or -d is provided, the CLI mode will be used, otherwise it will launch the GUI app"""
    )
    parser.add_argument("--log", default="INFO", help="Log level (default: INFO)")

    args = parser.parse_args()

    # Setup logger
    numeric_level = getattr(logging, args.log.upper(), None)
    logging.basicConfig(level=numeric_level)

    if args.extraction_types and args.data_path:

        logger.debug(f"Args: {args}")

    else:
        from gui import ConverterGUI

        logger.debug("GUI mode")
        ConverterGUI.start()
