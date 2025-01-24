from flask import Flask, request, send_file, render_template, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from PIL import Image
from datetime import datetime, timedelta, timezone
import os
import csv
import requests

app = Flask(__name__)

# 파일 정의 (Render 환경에서 /tmp 디렉터리를 사용)
LOG_FILE = "/tmp/email_tracking_log.csv"  # 열람 기록 로그
SEND_LOG_FILE = "/tmp/email_send_log.csv"  # 이메일 발송 로그

# KST 타임존 정의
KST = timezone(timedelta(hours=9))

# 픽셀 이미지 생성 함수
def create_pixel_image():
    """픽셀 이미지를 생성하여 저장합니다."""
    pixel_path = "/tmp/pixel.png"
    if not os.path.exists(pixel_path):
        pixel_image = Image.new("RGB", (1, 1), (255, 255, 255))  # 1x1 흰색 이미지 생성
        pixel_image.save(pixel_path)
        print("픽셀 이미지 생성 완료")
    return pixel_path

# CSV 파일 초기화
def initialize_csv_file_once(file_path, headers):
    """CSV 파일 초기화를 최초에 한 번만 실행합니다."""
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
            print(f"CSV 파일 초기화 완료: {file_path}")
        except Exception as e:
            print(f"CSV 초기화 오류: {e}")
    else:
        print(f"CSV 파일이 이미 존재합니다. 초기화를 건너뜁니다: {file_path}")

def reset_csv_file(file_path, headers):
    """CSV 파일을 초기화합니다."""
    try:
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        print(f"CSV 파일이 초기화되었습니다: {file_path}")
    except Exception as e:
        print(f"CSV 초기화 오류: {e}")

# CSV 파일 로드
def read_csv(file_path):
    """CSV 파일 로드 함수"""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return list(csv.reader(f))
    except Exception as e:
        print(f"CSV 읽기 오류: {e}")
        return []

# 로그 업데이트
def update_logs():
    """로그 파일 업데이트 함수 (5분마다 실행)"""
    logs = read_csv(LOG_FILE)
    if not logs:
        print("로그 파일이 비어 있습니다. 업데이트할 내용이 없습니다.")
        return

    print(f"로그 업데이트 진행 중... (총 {len(logs) - 1}개의 기록)")  # 첫 줄은 헤더 제외
    for row in logs[1:]:
        print({
            "timestamp": row[0],
            "email": row[1],
            "send_time": row[2],
            "ip": row[3],
            "user_agent": row[4],
        })

# 핑 기능
def ping_server():
    """서버 상태를 확인하는 핑 기능"""
    server_url = "https://tracking-g39r.onrender.com/"
    try:
        response = requests.get(server_url)
        if response.status_code == 200:
            print(f"핑 전송 성공: {response.status_code}")
        else:
            print(f"핑 전송 실패: {response.status_code}")
    except Exception as e:
        print(f"핑 전송 오류: {e}")

# APScheduler 설정
def schedule_tasks():
    """APScheduler로 주기적인 작업을 설정합니다."""
    scheduler = BackgroundScheduler()

    # 10분마다 서버 핑
    scheduler.add_job(ping_server, 'interval', minutes=10)

    # 5분마다 로그 업데이트
    scheduler.add_job(update_logs, 'interval', minutes=5)

    scheduler.start()
    print("APScheduler를 통해 작업이 스케줄링되었습니다.")

# 열람 기록 보기 및 초기화 버튼
@app.route("/logs", methods=["GET", "POST"])
def view_logs():
    """열람 기록 보기 및 초기화 버튼"""
    if request.method == "POST":
        # 초기화 버튼 눌렀을 때
        reset_csv_file(LOG_FILE, ["Timestamp (UTC+9, KST)", "Email", "Send Time", "Client IP", "User-Agent"])
        return redirect(url_for("view_logs"))

    logs = read_csv(LOG_FILE)
    if not logs:
        return render_template("logs.html", email_status=[], message="로그 파일이 없습니다.")

    viewed_logs = []
    for row in logs[1:]:  # 첫 번째 줄(헤더) 제외
        viewed_logs.append({
            "timestamp": f"{row[0]} (UTC+9, KST)",
            "email": row[1],
            "send_time": row[2],
            "ip": row[3],
            "user_agent": row[4]
        })

    return render_template("logs.html", email_status=viewed_logs, message="")

# 애플리케이션 초기화
def initialize_application():
    """애플리케이션 초기화 작업"""
    create_pixel_image()  # 픽셀 이미지 생성
    initialize_csv_file_once(LOG_FILE, ["Timestamp (UTC+9, KST)", "Email", "Send Time", "Client IP", "User-Agent"])
    initialize_csv_file_once(SEND_LOG_FILE, ["Email", "Send Time"])
    schedule_tasks()  # 작업 스케줄링 추가

# 애플리케이션 실행
if __name__ == "__main__":
    initialize_application()  # 초기화 작업은 여기서만 실행
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
