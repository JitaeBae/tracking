from flask import Flask, request, send_file, render_template, redirect, url_for
from datetime import datetime
import csv
import os

app = Flask(__name__)

# 파일 정의
LOG_FILE = "email_tracking_log.csv"  # 열람 기록 저장 파일
SENT_EMAILS_FILE = "sent_emails.csv"  # 업로드된 이메일 주소 저장 파일

@app.route("/")
def home():
    return "Flask 이메일 트래킹 시스템이 실행 중입니다."

# 이메일 주소 업로드 페이지
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

# 업로드된 이메일 주소 보기
@app.route("/uploaded-emails", methods=["GET"])
def view_uploaded_emails():
    emails = []
    if os.path.exists(SENT_EMAILS_FILE):
        with open(SENT_EMAILS_FILE, "r") as f:
            reader = csv.reader(f)
            emails = list(reader)[1:]  # 첫 줄(헤더) 제외
    return render_template("uploaded_emails.html", emails=emails)

# 트래킹 엔드포인트
@app.route("/track", methods=["GET"])
def track_email():
    # 이메일 열람 기록
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

# 열람 기록 보기
@app.route("/logs", methods=["GET"])
def view_logs():
    # 열람 기록 읽기
    with open(LOG_FILE, "r") as f:
        reader = csv.reader(f)
        viewed_logs = list(reader)[1:]  # 열람된 이메일의 전체 정보 가져오기 (헤더 제외)

    # 발송된 이메일 읽기
    with open(SENT_EMAILS_FILE, "r") as f:
        reader = csv.reader(f)
        sent_emails = [row[0] for row in list(reader)[1:]]  # 발송된 이메일 주소만 가져오기

    # 열람된 이메일 주소 목록
    viewed_emails = [log[1] for log in viewed_logs]

    # 열람되지 않은 이메일 계산
    not_viewed_emails = list(set(sent_emails) - set(viewed_emails))

    return render_template(
        "logs.html",
        viewed_logs=viewed_logs,
        not_viewed_emails=not_viewed_emails
    )

if __name__ == "__main__":
    # 로그 파일 초기화
    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Email", "Client IP", "User-Agent"])

    app.run(host="0.0.0.0", port=5000)
