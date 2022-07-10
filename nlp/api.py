#!/usr/bin/env python
from flask import Flask
from flask_cors import CORS
import util
from claritynlp_logging import log, setup_log, ERROR, DEBUG

import sys
import signal
from luigi_tools import luigi_runner

def create_app(config_filename=None):

    clarity_app = Flask(__name__)
    clarity_app.debug = True

    setup_log(clarity_app)

    if config_filename:
        clarity_app.config.from_pyfile(config_filename)

    from apis import ohdsi_app, phenotype_app, algorithm_app, utility_app
    clarity_app.register_blueprint(ohdsi_app)
    clarity_app.register_blueprint(phenotype_app)
    clarity_app.register_blueprint(algorithm_app)
    clarity_app.register_blueprint(utility_app)

    return clarity_app


# needs to be visible to Flask via import
application = create_app()
CORS(application)

# handler for CTRL-C, to shutdown worker threads
def _ctrl_c_handler(signal, frame):
    log('CTRL-C PRESSED')
    luigi_runner.shutdown_workers()
    sys.exit(0)

# install the singal handler for CTRL-C
signal.signal(signal.SIGINT, _ctrl_c_handler)


if __name__ == '__main__':
    log('starting claritynlp api...')
    application.run(host='0.0.0.0', port=5000, threaded=True, debug=True, use_reloader=False)
