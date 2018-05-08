"""Implementation of the REST API for the backbone service."""

import os
import flask
import logging
import requests
import io
from flask import Flask, request, current_app
from flask_cors import CORS

from utils import GithubRead, COREAPI_SERVER_URL_REST

RECOMMENDER_API_TOKEN=os.getenv('RECOMMENDER_API_TOKEN', None)

app = Flask(__name__)
CORS(app)


@app.route('/liveness')
def liveness():
    print('Liveness probe!')
    return flask.jsonify({})


@app.route('/api/v1/scan-container', methods=['POST'])
def scan_container():
    """Handle POST requests that are sent to /api/v1/scan-container REST API endpoint."""
    output = {}
    input_json = request.get_json()
    current_app.logger.debug('scan-container with payload: {p}'.format(p=input_json))
    if input_json and 'image' in input_json and input_json['image']:
        output['image'] = input_json['image']
        try:
            print('Retrieving the image into the system')
            # retrieve_image(input_json['image'])
            #
            # fetch_container_info(input_json['image'])
            #
            # print('removing the image from the system')
            # remove_image(input_json['image'])
            output['base-os'] = None
            output['runtime_status'] = None
        except Exception as e:
            current_app.logger.error(e)

    if input_json and 'git-url' in input_json and input_json['git-url']:
        print ('Input Git URL: %s' % input_json['git-url'])
        output['git-url'] = input_json['git-url']
        manifests = GithubRead().get_manifest_details(input_json['git-url'])
        print(manifests)

        stack_analyses_reqs = []
        for manifest in manifests:
            response = requests.get(manifest.get('download_url', ''))
            if response.status_code == 200:
                content = response.text
                manifest_file = io.StringIO(content)
                param = {'manifest[]': ('pom.xml',manifest_file)}
                endpoint = '{}/api/v1/stack-analyses'.format("https://recommender.api.openshift.io")
                print('Stack analyses request initiated for {}'.format(manifest.get('download_url', '')))
                response = requests.post(endpoint, files=param, data={'filePath[]': '/home/sam1'},
                                 headers={'Authorization': 'Bearer {}'.format(RECOMMENDER_API_TOKEN)})
                print('Response Code = %d' % response.status_code)
                print('Response:\n%r' % response.json())
                stack_analyses_reqs.append(response.json())
        output['stack-requests'] = stack_analyses_reqs
    return flask.jsonify(output)


if __name__ == "__main__":
    app.run()
