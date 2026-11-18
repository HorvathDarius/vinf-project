#!/bin/bash
# Run a Python script in the PyLucene image: ./run_lucene.sh src/<script>.py [args...]
# The image is built from Dockerfile.lucene read on stdin, so the 24 GB project folder is not sent as build context
docker build -q -t vinf-lucene - < Dockerfile.lucene > /dev/null || exit 1
# -t only when stdin is a terminal (interactive search), so output can still be redirected to a file
TTY_FLAG="-i"
[ -t 0 ] && [ -t 1 ] && TTY_FLAG="-it"
docker run --rm $TTY_FLAG \
  -v "$PWD":/project -w /project \
  -e PYTHONPATH=/project/src \
  vinf-lucene \
  python "$@"
