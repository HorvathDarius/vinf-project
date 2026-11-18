#!/bin/bash
# Run a PySpark job in the official Spark image: ./run_spark.sh src/<job>.py [args...]
# The image is built from Dockerfile read on stdin, so the 24 GB project folder is not sent as build context
docker build -q -t vinf-spark - < Dockerfile > /dev/null || exit 1
docker run --rm \
  -v "$PWD":/project -w /project \
  -e PYTHONPATH=/project/src \
  vinf-spark \
  /opt/spark/bin/spark-submit --master "local[*]" --driver-memory 10g "$@"
