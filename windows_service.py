# pyright: reportMissingModuleSource=false

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Thread

from dotenv import load_dotenv


APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")
os.environ["APP_ENV"] = "production"

LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[RotatingFileHandler(
        LOG_DIR / "chat-service.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )],
)

from waitress import serve

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
    from waitress.server import create_server
    WINDOWS_SERVICE_AVAILABLE = True
except ImportError:
    servicemanager = None
    win32event = None
    win32service = None
    win32serviceutil = None
    create_server = None
    WINDOWS_SERVICE_AVAILABLE = False

from server import app


if WINDOWS_SERVICE_AVAILABLE:
    class ChatSystemService(win32serviceutil.ServiceFramework):
        _svc_name_ = "ChatSystem"
        _svc_display_name_ = "Chat System"
        _svc_description_ = "Hosts the Chat System web application."

        def __init__(self, args):
            super().__init__(args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.http_server = None
            self.server_thread = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):
            logging.info("Starting Chat System service")
            host = os.environ.get("HOST", "127.0.0.1")
            port = int(os.environ.get("PORT", "5000"))
            threads = int(os.environ.get("WAITRESS_THREADS", "100"))
            self.http_server = create_server(app, host=host, port=port, threads=threads)
            self.server_thread = Thread(target=self._serve, name="waitress-server")
            self.server_thread.start()

            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
            self._stop_server()
            logging.info("Chat System service stopped")

        def _serve(self):
            try:
                self.http_server.run()
            except Exception:
                logging.exception("Waitress server stopped unexpectedly")
            finally:
                win32event.SetEvent(self.stop_event)

        def _stop_server(self):
            if self.http_server is None:
                return
            self.http_server.close()
            for channel in list(self.http_server.active_channels.values()):
                channel.close()
            self.http_server.task_dispatcher.shutdown(cancel_pending=False, timeout=10)
            if self.server_thread is not None:
                self.server_thread.join(timeout=15)
                if self.server_thread.is_alive():
                    logging.error("Waitress server thread did not stop cleanly")


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    threads = int(os.environ.get("WAITRESS_THREADS", "100"))
	
    if len(sys.argv) == 1 or sys.argv[1] == "run":
        logging.info("Starting production server on %s:%s", host, port)
        serve(app, host=host, port=port, threads=threads)
    elif WINDOWS_SERVICE_AVAILABLE:
        win32serviceutil.HandleCommandLine(ChatSystemService)
    else:
        raise RuntimeError("Windows service support is unavailable in this environment. Use 'python server.py' for local runs.")