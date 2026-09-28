# ===== 이메일 알림 =====
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from runtime_config import EMAIL_ADDRESS, EMAIL_PASSWORD, EMAIL_TO

def send_kakao_message(message):  # 함수명 유지 (main.py 호환)
    # 알림 메일 계정을 안 넣은 사람이 대부분이다. 그대로 두면 동기화가 다 끝난 뒤
    # 구글이 돌려주는 '535 Username and Password not accepted' 가 찍혀서
    # 방금 성공한 작업이 실패한 것처럼 보인다. 안 넣었으면 조용히 건너뛴다.
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD or not EMAIL_TO:
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = EMAIL_TO
        msg['Subject'] = "📚 DGIST LMS 새 파일 알림"
        msg.attach(MIMEText(message, 'plain', 'utf-8'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        print("이메일 전송 완료!")
        return True
    except Exception as e:
        print(f"이메일 전송 실패: {e}")
        return False
