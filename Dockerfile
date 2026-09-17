# syntax=docker/dockerfile:1
# 9주차 실습 랩 이미지. 코어·그래프·문이 한 프로세스에 살므로 이미지도 하나다.
# compose가 저장소를 /app에 바인드 마운트하므로 이미지에는 의존성만 담는다.
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1
