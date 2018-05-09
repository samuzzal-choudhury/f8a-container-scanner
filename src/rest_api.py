"""Implementation of the REST API for the backbone service."""

import os
import flask
import requests
import io
from flask import Flask, request, current_app
from flask_cors import CORS

from utils import GithubRead, COREAPI_SERVER_URL_REST, retrieve_image, fetch_container_info

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
            inp={"image": input_json['image']}
            resp=requests.post('http://35.232.131.171:5000/api/v1/image/info', json=inp)
        except Exception as e:
            current_app.logger.error(e)
            raise

        if resp.status_code == 200:
            data=resp.json()
            print(data)
            output['base-os'] = data['os']
            output['git-url'] = data['git-url']
        else:
            print('HTTP Error %d' % resp.status_code)

    if 'git-url' in output:
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


@app.route('/api/v1/image/info', methods=['POST'])
def image_info():
    data={}
    input_json = request.get_json()
    print('scan-container with payload: {p}'.format(p=input_json))
    if input_json and 'image' in input_json and input_json['image']:
        try:
            print('Retrieving the image into the system')
            retrieve_image(input_json['image'])

            data=fetch_container_info(input_json['image'])
        except Exception as e:
            current_app.logger.error(e)

    return flask.jsonify(data)


if __name__ == "__main__":
    app.run()
