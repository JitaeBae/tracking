from flask import Flask, request, send_file, render_template, redirect, url_for
from PIL import Image
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import csv
import os
import requests

app = Flask(__name__)

# 파일 정의
LOG_FILE = "email_tracking_log.csv"
SENT_EMAILS_FILE = "sent_emails.csv"
SELF_PING_URL = "https://tracking-g39r.onrender.com/"  # Replace with your deployed URL on Render

# 픽셀 이미지 생성 함수
def create_pixel_image():
    pixel_image = Image.new("RGB", (1, 1), (255, 255, 255))  # 1x1 흰색 이미지 생성
    pixel_image.save("pixel.png")  # pixel.png로 저장

# 파일 초기화 함수
def initialize_log_file():
    """로그 파일이 없거나 비어있으면 헤더 추가"""
    try:
        # 파일이 없거나 비어있으면 헤더 추가
        if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
            with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Email", "Client IP", "User-Agent"])
            print(f"로그 파일 {LOG_FILE} 초기화 완료")
    except Exception as e:
        print(f"로그 파일 초기화 오류: {e}")

# 애플리케이션 시작 시 픽셀 이미지 생성
def initialize_application():
    if not os.path.exists("pixel.png"):
        create_pixel_image()
    
    # 로그 파일 초기화
    initialize_log_file()

# 서버 상태 확인 엔드포인트
@app.route("/", methods=["GET"])
def home():
    return "서버가 잘 작동 중입니다. 이메일 트래킹 시스템이 실행 중입니다.", 200

# 이메일 업로드 페이지
@app.route("/upload", methods=["GET", "POST"])
def upload_emails():
    if request.method == "POST":
        uploaded_file = request.files["file"]
        if uploaded_file.filename.endswith(".csv"):
            uploaded_file.save(SENT_EMAILS_FILE)
            return redirect(url_for("view_uploaded_emails"))
        else:
            return "CSV 파일만 업로드 가능합니다.", 400
    return render_template("upload.html")

# 업로드된 이메일 확인
@app.route("/uploaded-emails", methods=["GET"])
def view_uploaded_emails():
    emails = []
    if os.path.exists(SENT_EMAILS_FILE):
        with open(SENT_EMAILS_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            emails = list(reader)[1:]
    else:
        return "업로드된 파일이 없습니다.", 404
    return render_template("uploaded_emails.html", emails=emails)

@app.route("/track", methods=["GET"])
def track_email():
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    email = request.args.get("email")

    if not email:
        print("이메일 파라미터가 없습니다.")
        return "이메일 파라미터가 없습니다.", 400

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 로그 파일에 데이터 기록
    try:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, email, client_ip, user_agent])
        print(f"Tracking email: {email}, IP: {client_ip}, User-Agent: {user_agent}")
    except Exception as e:
        print(f"로그 파일 쓰기 오류: {e}")
        return "로그 파일 쓰기 오류", 500

    # 픽셀 이미지 반환
    if not os.path.exists("pixel.png"):
        create_pixel_image()  # 픽셀 이미지 생성 함수 호출
    return send_file("pixel.png", mimetype="image/png")

# 열람 기록 보기
@app.route("/logs", methods=["GET"])
def view_logs():
    if not os.path.exists(LOG_FILE):
        return "로그 파일이 없습니다.", 404
    
    viewed_logs = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        viewed_logs = list(reader)[1:]

    sent_emails = []
    if os.path.exists(SENT_EMAILS_FILE):
        with open(SENT_EMAILS_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            sent_emails = [row[0] for row in list(reader)[1:]]

    email_status = []
    for email in sent_emails:
        if any(log[1] == email for log in viewed_logs):
            log = next(log for log in viewed_logs if log[1] == email)
            email_status.append({
                "email": email,
                "status": "열람",
                "timestamp": log[0],
                "ip": log[2],
                "user_agent": log[3]
            })
        else:
            email_status.append({
                "email": email,
                "status": "미열람",
                "timestamp": None,
                "ip": None,
                "user_agent": None
            })
    return render_template("logs.html", email_status=email_status)

# Self-Ping 작업
def self_ping():
    try:
        response = requests.get(SELF_PING_URL)
        if response.status_code == 200:
            print("Self-Ping 성공: 서버가 작동 중입니다.")
        else:
            print(f"Self-Ping 실패: 상태 코드 {response.status_code}")
    except Exception as e:
        print(f"Self-Ping 오류: {e}")

# 주기적인 작업
def check_email_logs():
    try:
        print("열람 로그와 발송된 이메일 목록을 주기적으로 비교 중...")
        viewed_logs = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                viewed_logs = list(reader)[1:]

        sent_emails = []
        if os.path.exists(SENT_EMAILS_FILE):
            with open(SENT_EMAILS_FILE, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                sent_emails = [row[0] for row in list(reader)[1:]]

        viewed_emails = [log[1] for log in viewed_logs]
        not_viewed_emails = list(set(sent_emails) - set(viewed_emails))

        print(f"열람된 이메일: {viewed_emails}")
        print(f"열람되지 않은 이메일: {not_viewed_emails}")
    except Exception as e:
        print(f"Scheduler Error: {e}")

# APScheduler 설정
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_email_logs, trigger="interval", minutes=10)  # 이메일 로그 비교 작업
scheduler.add_job(func=self_ping, trigger="interval", minutes=5)  # Self-Ping 작업
scheduler.start()

# 애플리케이션 시작 전 초기화 호출
initialize_application()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
