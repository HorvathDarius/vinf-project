#!/bin/bash
# Run a PySpark job in the course image: ./run_spark.sh src/<job>.py [args...]
docker run --rm --platform linux/amd64 \
  -v "$PWD":/project -w /project \
  -e PYSPARK_PYTHON=python3 \
  -e PYTHONPATH=/project/src \
  -e LANG=C.UTF-8 -e PYTHONIOENCODING=utf-8 \
  --entrypoint bash \
  iisas/hadoop-spark-pig-hive:2.9.2 \
  -c 'export SPARK_DIST_CLASSPATH=$(hadoop classpath); spark-submit --master "local[*]" --driver-memory 10g "$@"' _ "$@"