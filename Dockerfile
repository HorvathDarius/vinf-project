# Official Spark image (Spark 4.3.0, Java 21, Python 3.10) + requests, which common.py imports
FROM apache/spark:4.3.0-python3
USER root
RUN pip install --no-cache-dir requests
USER spark
