import os
import requests
from flask import Flask, request, send_file, render_template, jsonify, redirect, url_for, make_response
from PIL import Image
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler

# ========= SQLAlchemy & DB 연결 설정 =========
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# Flask 앱 생성
app = Flask(__name__)

# ------------------------
# 1. 환경 변수/타임존/기타
# ------------------------
DATABASE_URL = os.getenv("DATABASE_URL")  # ex) "postgresql://user:pass@host:port/db"
KST = timezone(timedelta(hours=9))

# (과거 CSV 파일 이름이었지만, DB 사용으로 대체)
# DB에는 테이블로 저장하므로 LOG_FILE, SEND_LOG_FILE은 의미상만 남겨둠
LOG_FILE = os.getenv("LOG_FILE_PATH", "email_tracking_log.csv")
SEND_LOG_FILE = os.getenv("SEND_LOG_FILE_PATH", "email_send_log.csv")

# -----------------------
# 2. SQLAlchemy 초기 설정
# -----------------------
engine = create_engine(DATABASE_URL, echo=False)  # echo=True로 하면 SQL 로그가 콘솔에 출력
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------------------
# 3. DB 테이블(ORM 모델) 정의
# -----------------------------
class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    email = Column(String, nullable=False)
    send_time = Column(String)   # 과거 CSV에선 문자열로 기록
    client_ip = Column(String)
    user_agent = Column(String)

class EmailSendLog(Base):
    __tablename__ = "email_send_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    send_time = Column(String)

# ---------------------
# 4. DB 초기화 함수
# ---------------------
def init_db():
    Base.metadata.create_all(bind=engine)
    print("DB 테이블 생성(또는 이미 존재).")

# -------------------------
# 5. 유틸리티 / 일반 함수
# -------------------------
def create_pixel_image():
    """픽셀 이미지를 생성하여 /tmp/pixel.png 경로에 저장, 경로 반환"""
    pixel_path = os.getenv("PIXEL_IMAGE_PATH", "/tmp/pixel.png")
    if not os.path.exists(pixel_path):
        try:
            pixel_image = Image.new("RGB", (1, 1), (255, 255, 255))
            pixel_image.save(pixel_path)
            print("픽셀 이미지 생성 완료")
        except Exception as e:
            print(f"픽셀 이미지 생성 오류: {e}")
    return pixel_path

def get_email_send_time(email):
    """DB에서 email에 해당하는 발송 시간을 찾거나, 없으면 '발송 기록 없음'"""
    db = SessionLocal()
    try:
        record = db.query(EmailSendLog).filter(EmailSendLog.email == email).first()
        if record:
            return record.send_time
        else:
            return "발송 기록 없음"
    finally:
        db.close()

def log_email_send(email):
    """이메일 발송 기록 저장 (과거 CSV -> DB)"""
    db = SessionLocal()
    try:
        send_time = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        new_record = EmailSendLog(email=email, send_time=send_time)
        db.add(new_record)
        db.commit()
        print(f"이메일 발송 기록 저장: {email}, 발송 시간: {send_time}")
    except Exception as e:
        db.rollback()
        print(f"이메일 발송 기록 오류: {e}")
    finally:
        db.close()

# -----------------
# 6. 라우트 정의
# -----------------

@app.route("/", methods=["GET"])
def home():
    """서버 상태 확인"""
    print("홈 라우트에 접근했습니다.")
    return jsonify({"status": "running", "message": "이메일 트래킹 시스템이 실행 중입니다."}), 200

@app.route("/track", methods=["GET"])
def track_email():
    """이메일 열람 트래킹 (DB에 저장)"""
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    email = request.args.get("email")

    if not email:
        return "이메일 파라미터가 없습니다.", 400

    # KST 타임스탬프
    timestamp = datetime.now(KST)
    # 이메일 발송 시간 조회
    send_time = get_email_send_time(email)

    # DB에 기록
    db = SessionLocal()
    try:
        new_log = EmailLog(
            timestamp=timestamp,
            email=email,
            send_time=send_time,
            client_ip=client_ip,
            user_agent=user_agent
        )
        db.add(new_log)
        db.commit()
        print(f"Tracking email: {email}, Send Time: {send_time}, IP: {client_ip}")
    except Exception as e:
        db.rollback()
        print(f"열람 기록 저장 오류: {e}")
        return "열람 기록 저장 오류", 500
    finally:
        db.close()

    # 픽셀 이미지 반환
    return send_file(create_pixel_image(), mimetype="image/png")

@app.route("/logs", methods=["GET", "POST"])
def view_logs():
    """열람 기록 보기 (GET) / 초기화 (POST)"""
    db = SessionLocal()

    try:
        if request.method == "POST":
            # 전체 로그 삭제
            db.query(EmailLog).delete()
            db.commit()
            print("로그 데이터 초기화 완료.")
            return redirect(url_for("view_logs"))

        # GET: 로그 조회
        logs = db.query(EmailLog).all()
        if not logs:
            return render_template("logs.html", email_status=[], feedback_message="No logs available.")

        viewed_logs = []
        for row in logs:
            viewed_logs.append({
                "timestamp": row.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "email": row.email,
                "send_time": row.send_time,
                "ip": row.client_ip,
                "user_agent": row.user_agent
            })

        return render_template("logs.html", email_status=viewed_logs, feedback_message=None)

    except Exception as e:
        print(f"로그 조회 오류: {e}")
        return "로그 조회 오류", 500
    finally:
        db.close()

@app.route("/download_log", methods=["GET"])
def download_log():
    """트래킹 로그를 CSV 파일 형태로 다운로드 (DB -> 메모리 -> 응답)"""
    import csv
    import io

    db = SessionLocal()
    try:
        logs = db.query(EmailLog).all()
        if not logs:
            return "No log records to download.", 200

        # 메모리에 CSV 작성
        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n')

        # 헤더
        writer.writerow(["Timestamp (UTC+9, KST)", "Email", "Send Time", "Client IP", "User-Agent"])

        # 데이터
        for row in logs:
            writer.writerow([
                row.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                row.email,
                row.send_time,
                row.client_ip,
                row.user_agent
            ])

        output.seek(0)

        # Flask 응답으로 CSV 파일 전송
        from flask import make_response
        response = make_response(output.read())
        response.headers["Content-Disposition"] = "attachment; filename=email_tracking_log.csv"
        response.headers["Content-Type"] = "text/csv"
        return response

    except Exception as e:
        print(f"CSV 다운로드 오류: {e}")
        return "CSV 다운로드 오류", 500
    finally:
        db.close()

# ---------------
# 7. 핑 & 스케줄
# ---------------
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

def schedule_tasks():
    """APScheduler로 주기적인 작업을 설정"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(ping_server, 'interval', minutes=10)  # 10분마다 ping
    scheduler.start()
    print("APScheduler를 통해 작업이 스케줄링되었습니다.")
    scheduler.print_jobs()

# ----------------------
# 8. 애플리케이션 초기화
# ----------------------
def initialize_application():
    """애플리케이션 초기화 작업"""
    # DB 테이블 생성
    init_db()

    # 픽셀 이미지 생성
    create_pixel_image()

    # 스케줄링
    schedule_tasks()

# -------------------
# 9. 앱 실행 (로컬)
# -------------------
#if __name__ == "__main__":
#    initialize_application()
#    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
