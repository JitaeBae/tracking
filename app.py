from flask import Flask, request, send_file, render_template
from PIL import Image
from datetime import datetime
import csv
import os

app = Flask(__name__)

# 파일 정의
LOG_FILE = "email_tracking_log.csv"

# 픽셀 이미지 생성 함수
def create_pixel_image():
    """픽셀 이미지를 생성하여 저장합니다."""
    pixel_image = Image.new("RGB", (1, 1), (255, 255, 255))  # 1x1 흰색 이미지 생성
    pixel_image.save("pixel.png")  # pixel.png로 저장

# 파일 초기화 함수
def initialize_log_file():
    """로그 파일이 없거나 비어있으면 헤더를 추가합니다."""
    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Email", "Client IP", "User-Agent"])

# 애플리케이션 초기화
def initialize_application():
    """애플리케이션 초기화 작업."""
    if not os.path.exists("pixel.png"):
        create_pixel_image()
    initialize_log_file()

# 서버 상태 확인 엔드포인트
@app.route("/", methods=["GET"])
def home():
    """서버 상태 확인"""
    return "서버가 잘 작동 중입니다. 이메일 트래킹 시스템이 실행 중입니다.", 200

# 트래킹 엔드포인트
@app.route("/track", methods=["GET"])
def track_email():
    """이메일 열람 트래킹"""
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
        create_pixel_image()
    return send_file("pixel.png", mimetype="image/png")

# 열람 기록 보기
@app.route("/logs", methods=["GET"])
def view_logs():
    """열람 기록 보기"""
    if not os.path.exists(LOG_FILE):
        return "로그 파일이 없습니다.", 404
    
    # 로그 파일 읽기
    viewed_logs = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in list(reader)[1:]:  # 첫 번째 줄(헤더) 제외
            viewed_logs.append({
                "timestamp": row[0],
                "email": row[1],
                "ip": row[2],
                "user_agent": row[3]
            })

    return render_template("logs.html", email_status=viewed_logs)

# 애플리케이션 초기화 호출
initialize_application()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
