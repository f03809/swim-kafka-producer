FROM python:3.12-slim

WORKDIR /src
COPY . /src

RUN pip install --no-cache-dir /src

USER 65534:65534

CMD ["python", "-m", "app.main"]
