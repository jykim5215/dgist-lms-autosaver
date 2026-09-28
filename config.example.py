# ===== 설정 파일 예시 =====
# setup.py 실행하면 자동으로 config.py 가 생성됩니다.
# 이 파일을 직접 수정하지 마세요.

LMS_ID = "your_student_id"
LMS_PASSWORD = "your_password"

GEMINI_API_KEY = "your_gemini_api_key"

# 공공데이터포털(data.go.kr)에서 발급받는 인증키.
# 개설강좌·학사일정·세미나행사 정보를 공식 API로 받아올 때 쓴다.
# 비워 두면 예전처럼 학교 홈페이지를 긁어 오는 방식으로 동작한다.
# 인코딩키·디코딩키 어느 쪽을 넣어도 된다.
DGIST_API_KEY = ""

EMAIL_ADDRESS = "your_gmail@gmail.com"
EMAIL_PASSWORD = "your_app_password"
EMAIL_TO = "your_gmail@gmail.com"

DOWNLOAD_PATH = r"C:\lms-autosaver\downloads"
SCHEDULE_TIME = "08:00"

LMS_URL = "https://lms.dgist.ac.kr"
LOGIN_URL = "https://saml.dgist.ac.kr/authentication/idpw/idPwLogin.html?agentId=-100000&useOauth=0"
