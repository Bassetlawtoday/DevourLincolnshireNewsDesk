import customtkinter as ctk
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from modules.dashboard import Dashboard
from database.database import create_database
from newsdesk.ui_support import maximize_window
from newsdesk.maintenance import run_startup_maintenance


def configure_logging():
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    file_handler = RotatingFileHandler(
        log_dir / "newsdesk.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logging.basicConfig(
        level=logging.INFO,
        handlers=(file_handler, console_handler),
        force=True,
    )


def main():
    configure_logging()
    run_startup_maintenance()
    create_database()

    root = ctk.CTk()

    root.geometry("1400x900")

    Dashboard(root)
    root.after_idle(lambda: maximize_window(root))

    root.mainloop()


if __name__ == "__main__":

    main()
