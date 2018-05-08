"""Implementation of the REST API for the backbone service."""

import os
import flask
import logging
from flask import Flask, request, current_app
from flask_cors import CORS

from utils import retrieve_image, remove_image, fetch_container_info


def setup_logging(flask_app):
    """Perform the setup of logging (file, log level) for this application."""
    if not flask_app.debug:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'))
        log_level = os.environ.get('FLASK_LOGGING_LEVEL', logging.getLevelName(logging.WARNING))
        handler.setLevel(log_level)

        flask_app.logger.addHandler(handler)
        flask_app.config['LOGGER_HANDLER_POLICY'] = 'never'
        flask_app.logger.setLevel(logging.DEBUG)


app = Flask(__name__)
setup_logging(app)
CORS(app)


@app.route('/liveness')
def liveness():
    print('Liveness probe!')
    return flask.jsonify({})


@app.route('/api/v1/scan-container', methods=['POST'])
def scan_container():
    """Handle POST requests that are sent to /api/v1/scan-container REST API endpoint."""
    input_json = request.get_json()
    current_app.logger.debug('scan-container with payload: {p}'.format(p=input_json))
    if input_json and 'image' in input_json and input_json['image']:
        try:
            print('Retrieving the image into the system')
            retrieve_image(input_json['image'])

            fetch_container_info(input_json['image'])

            print('removing the image from the system')
            remove_image(input_json['image'])
        except Exception as e:
            current_app.logger.error(e)

    if input_json and 'git-url' in input_json and input_json['git-url']:


    return flask.jsonify({})


if __name__ == "__main__":
    app.run()
