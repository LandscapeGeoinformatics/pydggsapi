from gunicorn.app.wsgiapp import WSGIApplication
# from gunicorn.app.base import BaseApplication
from dotenv import load_dotenv
import logging
import os

# Reference from :
# https://stackoverflow.com/questions/70396641/how-to-run-gunicorn-inside-python-not-as-a-command-line


class StandaloneApplication(WSGIApplication):
    def __init__(self, app_uri, options=None):
        self.options = options or {}
        self.app_uri = app_uri
        super().__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)


def run():
    load_dotenv()
    bind = os.environ.get('bind', '0.0.0.0:8000')
    workers = os.environ.get('workers', 4)
    timeout = os.environ.get('worker_timeout', 120)
    options = {
        "bind": bind,
        "workers": workers,
        "worker_class": "uvicorn.workers.UvicornWorker",
        "timeout": timeout
    }
    log_level = os.environ.get('LOGLEVEL', logging.INFO)
    # set up logging for app as console output
    logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s {%(module)s} [%(funcName)s] %(message)s',
                        datefmt='%Y-%m-%d,%H:%M:%S', level=int(log_level))
    if (os.environ.get('dggs_api_config') is None):
        raise Exception("Env variable dggs_api_config is not set.")
    StandaloneApplication("pydggsapi.api:app", options).run()


if __name__ == '__main__':
    load_dotenv()
    bind = os.environ.get('bind', '0.0.0.0:8000')
    workers = os.environ.get('workers', 4)
    timeout = os.environ.get('worker_timeout', 120)
    options = {
        "bind": bind,
        "workers": workers,
        "worker_class": "uvicorn.workers.UvicornWorker",
        "timeout": timeout
    }

    log_level = os.environ.get('LOGLEVEL', logging.INFO)
    # set up logging for app as console output
    logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s {%(module)s} [%(funcName)s] %(message)s',
                        datefmt='%Y-%m-%d,%H:%M:%S', level=int(log_level))
    if (os.environ.get('dggs_api_config') is None):
        raise Exception("Env variable dggs_api_config is not set.")
    StandaloneApplication("pydggsapi.api:app", options).run()
