FROM python:3.12-slim

# Render(웹 호스팅)에는 앱 대신 '설치 파일 받기' 안내 페이지만 띄운다.
# 무료 서버에서는 LMS 동기화가 메모리·잠들기 때문에 계속 실패했고, 학교 비밀번호가
# 서버에 평문으로 남았다. 자세한 사정은 hosted_notice.py 머리말.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY hosted_notice.py .
COPY web/favicon.svg web/favicon.svg
COPY web/img/dalgu/hello.png web/img/dalgu/hello.png

EXPOSE 8765

CMD ["python", "hosted_notice.py"]
