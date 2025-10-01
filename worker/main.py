import asyncio
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main() -> None:
    """Entrypoint for the placeholder worker loop."""
    logging.info("Worker booted. Add task orchestration here.")
    logging.info("Current timestamp: %s", datetime.utcnow().isoformat())
    # Keep the process alive to mimic a long-running worker without doing work.
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Worker shutdown requested. Bye!")
