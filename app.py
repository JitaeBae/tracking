from flask import Flask, request, send_file, render_template, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import csv
import os

app = Flask(__name__)

# 파일 정의
LOG_FILE = "email_tracking_log.csv"  # 열람 기록 저장 파일
SENT_EMAILS_FILE = "sent_emails.csv"  # 발송된 이메일 주소 저장 파일

# 이메일 업로드 페이지
@app.route("/upload", methods=["GET", "POST"])
def upload_emails():
    if request.method == "POST":
        # 업로드된 파일 가져오기
        uploaded_file = request.files["file"]
        if uploaded_file.filename.endswith(".csv"):
            # 파일 저장
            uploaded_file.save(SENT_EMAILS_FILE)
            return redirect(url_for("view_uploaded_emails"))
        else:
            return "CSV 파일만 업로드 가능합니다.", 400
    return render_template("upload.html")

@app.route("/uploaded-emails", methods=["GET"])
def view_uploaded_emails():
    emails = []
    # 파일 존재 여부 확인
    if os.path.exists(SENT_EMAILS_FILE):
        with open(SENT_EMAILS_FILE, "r") as f:
            reader = csv.reader(f)
            emails = list(reader)[1:]  # 첫 줄(헤더) 제외
    else:
        # 파일이 없을 경우 메시지 반환
        return "업로드된 파일이 없습니다.", 404

    # 파일이 존재하면 HTML 템플릿 렌더링
    return render_template("uploaded_emails.html", emails=emails)


# 트래킹 엔드포인트
@app.route("/track", methods=["GET"])
def track_email():
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    email = request.args.get("email")  # 쿼리에서 이메일 주소 가져오기
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 로그 기록
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, email, client_ip, user_agent])

    # 투명한 1x1 픽셀 반환
    return send_file("pixel.png", mimetype="image/png")

@app.route("/logs", methods=["GET"])
def view_logs():
    # 로그 파일 존재 여부 확인
    if not os.path.exists(LOG_FILE):
        # 로그 파일이 없을 경우 메시지 반환
        return "로그 파일이 없습니다.", 404

    # 열람 기록 읽기
    viewed_logs = []
    with open(LOG_FILE, "r") as f:
        reader = csv.reader(f)
        viewed_logs = list(reader)[1:]  # 첫 줄(헤더) 제외

    # 발송된 이메일 읽기
    sent_emails = []
    if os.path.exists(SENT_EMAILS_FILE):
        with open(SENT_EMAILS_FILE, "r") as f:
            reader = csv.reader(f)
            sent_emails = [row[0] for row in list(reader)[1:]]  # 발송된 이메일 주소만 가져오기

    # 이메일별 열람 여부 데이터 생성
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

    # 템플릿 렌더링
    return render_template("logs.html", email_status=email_status)


# 주기적인 작업: 열람 로그와 발송된 이메일 목록 비교
def check_email_logs():
    try:
        print("열람 로그와 발송된 이메일 목록을 주기적으로 비교 중...")
        viewed_logs = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                reader = csv.reader(f)
                viewed_logs = list(reader)[1:]  # 열람된 이메일의 전체 정보 가져오기

        sent_emails = []
        if os.path.exists(SENT_EMAILS_FILE):
            with open(SENT_EMAILS_FILE, "r") as f:
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
scheduler.add_job(func=check_email_logs, trigger="interval", minutes=10)  # 10분마다 실행
scheduler.start()

if __name__ == "__main__":
    # 초기화: 로그 파일 생성
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Email", "Client IP", "User-Agent"])

    app.run(host="0.0.0.0", port=5000)
