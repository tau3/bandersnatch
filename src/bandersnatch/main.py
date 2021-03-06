import argparse
import asyncio
import configparser
import logging
import logging.config
import os.path
import shutil

import bandersnatch.log
import bandersnatch.master
import bandersnatch.mirror
import bandersnatch.utils
import bandersnatch.verify

from .configuration import BandersnatchConfig

logger = logging.getLogger(__name__)


def mirror(config):
    # Always reference those classes here with the fully qualified name to
    # allow them being patched by mock libraries!
    master = bandersnatch.master.Master(
        config.get("mirror", "master"), config.getfloat("mirror", "timeout")
    )

    # `json` boolean is a new optional option in 2.1.2 - want to support it
    # not existing in old configs and display an error saying that this will
    # error in the not to distance release
    try:
        json_save = config.getboolean("mirror", "json")
    except configparser.NoOptionError:
        logger.error(
            "Please update your config to include a json "
            "boolean in the [mirror] section. Setting to False"
        )
        json_save = False

    try:
        root_uri = config.get("mirror", "root_uri")
    except configparser.NoOptionError:
        root_uri = None

    try:
        digest_name = config.get("mirror", "digest_name")
    except configparser.NoOptionError:
        digest_name = "sha256"
    if digest_name not in ("md5", "sha256"):
        logger.error(
            "Supplied digest_name {0} is not supported! Please update"
            "digest_name to one of ('sha256', 'md5') in the [mirror]"
            "section."
        )

    mirror = bandersnatch.mirror.Mirror(
        config.get("mirror", "directory"),
        master,
        stop_on_error=config.getboolean("mirror", "stop-on-error"),
        workers=config.getint("mirror", "workers"),
        hash_index=config.getboolean("mirror", "hash-index"),
        json_save=json_save,
        root_uri=root_uri,
        digest_name=digest_name,
    )

    changed_packages = mirror.synchronize()
    logger.info("{} packages had changes".format(len(changed_packages)))
    for package_name, changes in changed_packages.items():
        logger.debug(f"{package_name} added: {changes}")


def main():
    parser = argparse.ArgumentParser(description="PyPI PEP 381 mirroring client.")
    parser.add_argument(
        "-c",
        "--config",
        default="/etc/bandersnatch.conf",
        help="use configuration file (default: %(default)s)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Turn on extra logging (DEBUG level)",
    )
    subparsers = parser.add_subparsers()

    # `mirror` command
    m = subparsers.add_parser(
        "mirror",
        help="Performs a one-time synchronization with the PyPI master server.",
    )
    m.set_defaults(op="mirror")

    # `verify` command
    v = subparsers.add_parser(
        "verify", help="Read in Metadata and check package file validity"
    )
    v.add_argument(
        "--delete",
        action="store_true",
        default=False,
        help="Enable deletion of packages not active",
    )
    v.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Do not download or delete files",
    )
    v.add_argument(
        "--json-update",
        action="store_true",
        default=False,
        help="Enable updating JSON from PyPI",
    )
    v.add_argument(
        "--workers",
        type=int,
        default=0,
        help="# of parallel iops [Defaults to bandersnatch.conf]",
    )
    v.set_defaults(op="verify")

    args = parser.parse_args()

    bandersnatch.log.setup_logging(args)

    # Prepare default config file if needed.
    default_config = os.path.join(os.path.dirname(__file__), "default.conf")
    if not os.path.exists(args.config):
        logger.warning(f"Config file '{args.config}' missing, creating default config.")
        logger.warning("Please review the config file, then run 'bandersnatch' again.")
        try:
            shutil.copy(default_config, args.config)
        except IOError as e:
            logger.error("Could not create config file: {}".format(str(e)))
        return 1

    config = configparser.ConfigParser()
    config.read([default_config, args.config])
    BandersnatchConfig(config_file=args.config)

    if config.has_option("mirror", "log-config"):
        logging.config.fileConfig(
            os.path.expanduser(config.get("mirror", "log-config"))
        )

    if args.op == "verify":
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(bandersnatch.verify.metadata_verify(config, args))
        finally:
            loop.close()
    else:
        mirror(config)


if __name__ == "__main__":
    main()
