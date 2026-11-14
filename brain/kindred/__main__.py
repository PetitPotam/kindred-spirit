"""python -m kindred  — start the brain (scripts/start.sh does this for you)."""
import argparse
import asyncio
import logging
import logging.handlers
import os
import sys

from . import config, hardware, server
from .server import run


def main():
    ap = argparse.ArgumentParser(prog="kindred", description="Kindred Spirit brain")
    ap.add_argument("--config", default=config.PATH, help="settings file (default %(default)s)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    log_dir = os.path.join(config.HOME, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.handlers.RotatingFileHandler(os.path.join(log_dir, "brain.log"), maxBytes=5_000_000, backupCount=2), logging.StreamHandler(sys.stderr)])
    logging.getLogger("websockets").setLevel(logging.INFO)  # frame-level logs would include audio
    for name in ("websockets.server", "websockets"):  # (health checks aren't failed handshakes, #180)
        logging.getLogger(name).addFilter(server.QuietProbes())
    cfg = config.load(args.config)
    cfg["_live_settings"] = args.config == config.PATH  # (changes from the dashboard are picked up live)
    token = config.read_or_create_token()
    hw = hardware.detect()
    logging.getLogger("kindred").info("settings: %s | this computer: %.0f GB, %d cores", args.config, hw["ram_gb"], hw["cores"])
    try:
        asyncio.run(run(cfg, token))
    except KeyboardInterrupt:
        pass
    except OSError as e:
        logging.getLogger("kindred").error("cannot listen on port %s: %s (is another brain running?)",
                                           cfg["server"]["port"], e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
