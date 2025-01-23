import threading
import requests
import os
from flask import Flask, request, send_file, render_template
from PIL import Image
from datetime import datetime, timedelta, timezone
import csv

app = Flask(__name__)

# 파일 정의
LOG_FILE = "email_tracking_log.csv"

# KST 타임존 정의
KST = timezone(timedelta(hours=9))

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
            writer.writerow(["Timestamp (UTC+9, KST)", "Email", "Client IP", "User-Agent"])
        print("로그 파일 초기화 완료")

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

    # KST 타임스탬프 생성
    timestamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    # 로그 파일에 데이터 기록
    try:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, email, client_ip, user_agent])
        print(f"Tracking email: {email}, IP: {client_ip}, User-Agent: {user_agent}, Timestamp: {timestamp}")
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
                "timestamp": f"{row[0]} (UTC+9, KST)",
                "email": row[1],
                "ip": row[2],
                "user_agent": row[3]
            })

    return render_template("logs.html", email_status=viewed_logs)

# 핑 기능
def keep_server_alive():
    """10분마다 서버 핑을 보내는 함수"""
    def ping():
        while True:
            try:
                # Render에서 실행 중인 서버 URL로 핑 전송
                server_url = os.environ.get("SERVER_URL", "http://127.0.0.1:5000/")
                response = requests.get(server_url)
                print(f"핑 전송 성공: {response.status_code}")
            except Exception as e:
                print(f"핑 전송 실패: {e}")
            
            # 10분 대기
            threading.Event().wait(600)
    
    # 백그라운드 스레드로 실행
    thread = threading.Thread(target=ping, daemon=True)
    thread.start()

# 애플리케이션 초기화
def initialize_application():
    """애플리케이션 초기화 작업"""
    if not os.path.exists("pixel.png"):
        create_pixel_image()
        print("픽셀 이미지 생성 완료")
    initialize_log_file()

# 애플리케이션 실행
if __name__ == "__main__":
    initialize_application()  # 초기화 작업은 여기서만 실행
    keep_server_alive()  # 핑 기능 실행
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
