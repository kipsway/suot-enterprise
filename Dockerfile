FROM python:3.12-slim-bookworm AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim-bookworm AS runner

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xfixes0 \
    libxcb-xkb1 libxkbcommon-x11-0 libgl1-mesa-glx libegl1-mesa \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

ENV PYTHONUNBUFFERED=1
ENV DISPLAY=${DISPLAY:-:0}

EXPOSE 8888

CMD ["python", "main.py"]
