FROM python:3.12-slim

COPY --chmod=0555 egress_gateway.py /usr/local/bin/egress_gateway.py

USER proxy
ENTRYPOINT ["python", "/usr/local/bin/egress_gateway.py"]
