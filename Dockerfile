FROM python:3.13.18-slim-trixie AS build
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13.18-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /srv
COPY --from=build /install /usr/local
COPY app ./app
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
RUN pip uninstall -y pip setuptools
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000
CMD [ "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" ]
