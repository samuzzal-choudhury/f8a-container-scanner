#!/usr/bin/bash

# Start API backbone service with time out
gunicorn --pythonpath /src/ -b 0.0.0.0:5000 -t 60000 -k gevent -w 2 rest_api:app
