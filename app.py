import threading
import requests
import os
from flask import Flask, request, send_file, render_template, jsonify
from PIL import Image
from datetime import datetime, timedelta, timezone
import csv
import time

app = Flask(__name__)

# 파일 정의 (환경 변수 또는 기본 경로)
LOG_FILE = os.getenv("LOG_FILE_PATH", "email_tracking_log.csv")
SEND_LOG_FILE = os.getenv("SEND_LOG_FILE_PATH", "email_send_log.csv")

# KST 타임존 정의
KST = timezone(timedelta(hours=9))

# 픽셀 이미지 생성 함수
def create_pixel_image():
    """픽셀 이미지를 생성하여 저장합니다."""
    pixel_path = os.getenv("PIXEL_IMAGE_PATH", "pixel.png")
    if not os.path.exists(pixel_path):
        try:
            pixel_image = Image.new("RGB", (1, 1), (255, 255, 255))  # 1x1 흰색 이미지 생성
            pixel_image.save(pixel_path)
            print("픽셀 이미지 생성 완료")
        except Exception as e:
            print(f"픽셀 이미지 생성 오류: {e}")
    return pixel_path

# CSV 파일 초기화
def initialize_csv_file(file_path, headers):
    """CSV 파일 초기화 함수"""
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
            print(f"CSV 파일 초기화 완료: {file_path}")
        except Exception as e:
            print(f"CSV 초기화 오류: {e}")

def read_csv(file_path):
    """CSV 파일 로드 함수"""
    if not os.path.exists(file_path):
        print(f"파일이 존재하지 않습니다: {file_path}")  # 디버깅 출력
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = list(csv.reader(f))
            print(f"읽은 데이터: {data}")  # 디버깅 출력
            return data
    except Exception as e:
        print(f"CSV 읽기 오류: {e}")  # 디버깅 출력
        return []


# 이메일 발송 기록 추가
def log_email_send(email):
    """이메일 발송 시간을 기록합니다."""
    send_time = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(SEND_LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([email, send_time])
            print(f"이메일 발송 기록 저장: {email}, 발송 시간: {send_time}")
    except Exception as e:
        print(f"이메일 발송 기록 오류: {e}")

# 이메일 발송 시간 조회
def get_email_send_time(email):
    """이메일 발송 시간을 조회합니다."""
    for row in read_csv(SEND_LOG_FILE):
        if row[0] == email:
            return row[1]
    return "발송 기록 없음"

# 서버 상태 확인 엔드포인트
@app.route("/", methods=["GET"])
def home():
    """서버 상태 확인"""
    return jsonify({"status": "running", "message": "이메일 트래킹 시스템이 실행 중입니다."}), 200

# 트래킹 엔드포인트
@app.route("/track", methods=["GET"])
def track_email():
    """이메일 열람 트래킹"""
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    email = request.args.get("email")

    if not email:
        return "이메일 파라미터가 없습니다.", 400

    # KST 타임스탬프 생성
    timestamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    # 이메일 발송 시간 조회
    send_time = get_email_send_time(email)

    # 열람 기록 추가
    try:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, email, send_time, client_ip, user_agent])
            print(f"Tracking email: {email}, Send Time: {send_time}, IP: {client_ip}")
    except Exception as e:
        print(f"열람 기록 저장 오류: {e}")
        return "열람 기록 저장 오류", 500

    # 픽셀 이미지 반환
    return send_file(create_pixel_image(), mimetype="image/png")

# 열람 기록 보기
@app.route("/logs", methods=["GET"])
def view_logs():
    """열람 기록 보기"""
    logs = read_csv(LOG_FILE)
    if not logs:
        return jsonify({"error": "로그 파일이 없습니다."}), 404

    viewed_logs = []
    for row in logs[1:]:  # 첫 번째 줄(헤더) 제외
        viewed_logs.append({
            "timestamp": f"{row[0]} (UTC+9, KST)",
            "email": row[1],
            "send_time": row[2],
            "ip": row[3],
            "user_agent": row[4]
        })

    return jsonify(viewed_logs), 200

# 핑 기능
def keep_server_alive(enabled=True):
    """10분마다 서버에 핑을 보내는 함수"""
    if not enabled:
        return

    server_url = os.getenv("SERVER_URL", "http://localhost:5000")
    
    def ping():
        while True:
            try:
                response = requests.get(server_url)
                if response.status_code == 200:
                    print(f"핑 전송 성공: {response.status_code}")
                else:
                    print(f"핑 전송 실패: {response.status_code}")
            except Exception as e:
                print(f"핑 전송 오류: {e}")
            
            # 10분 대기
            time.sleep(600)

    threading.Thread(target=ping, daemon=True).start()

# 애플리케이션 초기화
def initialize_application():
    """애플리케이션 초기화 작업"""
    create_pixel_image()  # 픽셀 이미지 생성
    initialize_csv_file(LOG_FILE, ["Timestamp (UTC+9, KST)", "Email", "Send Time", "Client IP", "User-Agent"])
    initialize_csv_file(SEND_LOG_FILE, ["Email", "Send Time"])

# 애플리케이션 실행
if __name__ == "__main__":
    initialize_application()  # 초기화 작업은 여기서만 실행
    keep_server_alive(enabled=True)  # 핑 기능 실행
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
