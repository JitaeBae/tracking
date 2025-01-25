import os
import csv
import requests
from flask import Flask, request, send_file, render_template, jsonify, redirect, url_for
from PIL import Image
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# 파일 정의 (환경 변수 또는 기본 경로)
LOG_FILE = os.getenv("LOG_FILE_PATH", "email_tracking_log.csv")
SEND_LOG_FILE = os.getenv("SEND_LOG_FILE_PATH", "email_send_log.csv")

# KST 타임존 정의
KST = timezone(timedelta(hours=9))

# 디렉토리 생성 함수
def create_directory_if_not_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"디렉토리 생성: {directory}")

# 애플리케이션 초기화 시 호출
create_directory_if_not_exists("./logs")


# 픽셀 이미지 생성 함수
def create_pixel_image():
    """픽셀 이미지를 생성하여 저장합니다."""
    pixel_path = os.getenv("PIXEL_IMAGE_PATH", "/tmp/pixel.png")
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
            with open(file_path, "w", newline="", encoding="euc-kr") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
            print(f"CSV 파일 초기화 완료: {file_path}")
        except Exception as e:
            print(f"CSV 초기화 오류: {e}")

def reset_csv_file(file_path, headers):
    """CSV 파일 초기화"""
    try:
        with open(file_path, "w", newline="", encoding="euc-kr") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        print(f"CSV 파일 초기화 완료: {file_path}")
    except Exception as e:
        print(f"CSV 초기화 오류: {e}")

def read_csv(file_path):
    """CSV 파일 로드 함수"""
    if not os.path.exists(file_path):
        print(f"파일이 존재하지 않습니다: {file_path}")
        return []
    try:
        with open(file_path, "r", encoding="euc-kr") as f:
            data = list(csv.reader(f))
            print(f"읽은 데이터: {data}")
            return data
    except Exception as e:
        print(f"CSV 읽기 오류: {e}")
        return []

# 이메일 발송 기록 추가
def log_email_send(email):
    """이메일 발송 시간을 기록합니다."""
    send_time = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(SEND_LOG_FILE, "a", newline="", encoding="euc-kr") as f:
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

@app.route("/", methods=["GET"])
def home():
    """서버 상태 확인"""
    print("홈 라우트에 접근했습니다.")
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
        with open(LOG_FILE, "a", newline="", encoding="euc-kr") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, email, send_time, client_ip, user_agent])
            print(f"Tracking email: {email}, Send Time: {send_time}, IP: {client_ip}")
    except Exception as e:
        print(f"열람 기록 저장 오류: {e}")
        return "열람 기록 저장 오류", 500

    # 픽셀 이미지 반환
    return send_file(create_pixel_image(), mimetype="image/png")

@app.route("/logs", methods=["GET", "POST"])
def view_logs():
    """열람 기록 보기 및 초기화 버튼"""
    if request.method == "POST":
        reset_csv_file(LOG_FILE, ["Timestamp (UTC+9, KST)", "Email", "Send Time", "Client IP", "User-Agent"])
        return redirect(url_for("view_logs"))

    # CSV 파일 읽기
    logs = read_csv(LOG_FILE)
    print(f"현재 읽은 로그 데이터: {logs}")

    if not logs or len(logs) <= 1:  # 헤더만 있는 경우
        return render_template("logs.html", email_status=[], feedback_message="No logs available.")

    # 로그 데이터 가공
    viewed_logs = []
    for row in logs[1:]:  # 첫 번째 줄(헤더) 제외
        viewed_logs.append({
            "timestamp": row[0],
            "email": row[1],
            "send_time": row[2],
            "ip": row[3],
            "user_agent": row[4]
        })

    print(f"가공된 로그 데이터: {viewed_logs}")

    # 템플릿으로 데이터 전달
    return render_template("logs.html", email_status=viewed_logs, feedback_message=None)

@app.route("/download_log", methods=["GET"])
def download_log():
    """트래킹 로그 파일 다운로드"""
    if os.path.exists(LOG_FILE):
        return send_file(
            LOG_FILE,
            as_attachment=True,
            mimetype="text/csv",
            attachment_filename="email_tracking_log.csv"
        )
    else:
        return "Log file not found.", 404

# 핑 기능
def ping_server():
    """서버 상태를 확인하는 핑 기능"""
    server_url = os.getenv("SERVER_URL", "https://tracking-g39r.onrender.com")
    try:
        print(f"핑 전송 시도 중: {server_url}")
        response = requests.get(server_url)
        if response.status_code == 200:
            print(f"핑 전송 성공: {response.status_code}")
        else:
            print(f"핑 전송 실패: {response.status_code}")
    except Exception as e:
        print(f"핑 전송 오류: {e}")

# APScheduler를 통한 작업 스케줄링
def schedule_tasks():
    """APScheduler로 주기적인 작업을 설정합니다."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(ping_server, 'interval', minutes=10)  # 10분마다 실행
    scheduler.start()
    print("APScheduler를 통해 작업이 스케줄링되었습니다.")
    scheduler.print_jobs()

# 애플리케이션 초기화
def initialize_application():
    """애플리케이션 초기화 작업"""
    create_directory_if_not_exists("./logs")  # 로그 디렉토리 생성
    create_pixel_image()  # 픽셀 이미지 생성
    initialize_csv_file(LOG_FILE, ["Timestamp (UTC+9, KST)", "Email", "Send Time", "Client IP", "User-Agent"])
    initialize_csv_file(SEND_LOG_FILE, ["Email", "Send Time"])
    schedule_tasks()  # 스케줄링 작업 추가


# 애플리케이션 실행
#if __name__ == "__main__":
#    initialize_application()  # 초기화 작업은 여기서만 실행
 #   app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
