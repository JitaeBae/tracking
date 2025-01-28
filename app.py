import os
import requests
from flask import Flask, request, send_file, render_template, jsonify, redirect, url_for, make_response
from PIL import Image
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, validates
from apscheduler.schedulers.background import BackgroundScheduler
from zoneinfo import ZoneInfo
import logging
import csv
import io

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logging.getLogger(__name__).setLevel(logging.DEBUG)

# Flask 앱 생성
app = Flask(__name__)

# 한국 표준시(KST) 정의
KST = ZoneInfo('Asia/Seoul')

# 환경 변수 설정
DATABASE_URL = os.getenv("DATABASE_URL")
PIXEL_IMAGE_PATH = os.getenv("PIXEL_IMAGE_PATH", "/tmp/pixel.png")

# SQLAlchemy 초기 설정
engine = create_engine(DATABASE_URL, echo=True, pool_pre_ping=True, connect_args={
    "sslmode": "require",
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5
})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# DB 테이블 정의
class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)  # 열람 시간 (UTC 저장)
    email = Column(String, nullable=False)
    send_time = Column(DateTime, nullable=True)  # 발송 시간 (UTC 저장)
    client_ip = Column(String)
    user_agent = Column(String)

class EmailSendLog(Base):
    __tablename__ = 'email_send_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    send_time = Column(DateTime(timezone=True), nullable=False)  # 발송 시간 (UTC 저장)

    @validates("send_time")
    def validate_send_time(self, key, send_time):
        """
        발송 시간을 UTC로 변환하여 저장
        """
        if isinstance(send_time, str):
            send_time = datetime.strptime(send_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST).astimezone(timezone.utc)
        elif isinstance(send_time, datetime) and send_time.tzinfo is None:
            send_time = send_time.replace(tzinfo=KST).astimezone(timezone.utc)
        return send_time

# 유틸리티 함수
def use_db_session(func):
    """데코레이터: DB 세션을 자동 관리"""
    def wrapper(*args, **kwargs):
        with SessionLocal() as db:
            try:
                return func(db, *args, **kwargs)
            except Exception as e:
                db.rollback()
                app.logger.error(f"DB 작업 오류: {e}")
                raise e
    return wrapper

def format_time_to_kst(time_value):
    """
    UTC 시간을 KST로 변환하고 포맷
    """
    if time_value:
        if isinstance(time_value, str):
            time_value = datetime.fromisoformat(time_value)
        return time_value.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    return "발송 기록 없음"

def get_or_create_pixel_image():
    """픽셀 이미지를 생성 또는 반환"""
    if not os.path.exists(PIXEL_IMAGE_PATH):
        pixel_image = Image.new("RGB", (1, 1), (255, 255, 255))
        pixel_image.save(PIXEL_IMAGE_PATH)
        app.logger.info("픽셀 이미지 생성 완료")
    return PIXEL_IMAGE_PATH

# DB 초기화 함수
def init_db():
    Base.metadata.create_all(bind=engine)
    app.logger.info("DB 테이블 생성 또는 확인 완료.")

# DB 작업 함수
@use_db_session
def log_email(db, email, send_time):
    """이메일 발송 기록 저장 (UTC 변환)"""
    if isinstance(send_time, str):
        send_time = datetime.strptime(send_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST).astimezone(timezone.utc)
    new_record = EmailSendLog(email=email, send_time=send_time)
    db.add(new_record)
    db.commit()

@use_db_session
def track_email_log(db, email, client_ip, user_agent):
    """이메일 열람 기록 저장 (UTC 일관성 보장)"""
    timestamp = datetime.now(timezone.utc)  # 현재 열람 시간 (UTC)
    send_time = get_email_send_time(db, email)  # UTC로 가져온 발송 시간
    new_log = EmailLog(
        timestamp=timestamp,
        email=email,
        send_time=send_time,  # 이미 UTC로 저장된 값 사용
        client_ip=client_ip,
        user_agent=user_agent
    )
    db.add(new_log)
    db.commit()

@use_db_session
def get_email_send_time(db, email):
    """DB에서 email에 해당하는 발송 시간을 UTC로 반환"""
    record = db.query(EmailSendLog).filter(EmailSendLog.email == email).first()
    if record:
        return record.send_time  # 이미 UTC로 저장된 값 반환
    return None

# Flask 라우트
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "message": "이메일 트래킹 시스템 실행 중"}), 200

@app.route("/track", methods=["GET"])
def track_email():
    email = request.args.get("email")
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")

    if not email:
        return "이메일 파라미터가 없습니다.", 400

    try:
        track_email_log(email=email, client_ip=client_ip, user_agent=user_agent)
        return send_file(get_or_create_pixel_image(), mimetype="image/png")
    except Exception as e:
        app.logger.error(f"Tracking error: {e}")
        return "Tracking error", 500

@app.route("/log-email", methods=["POST"])
def log_email_api():
    """클라이언트에서 발송 시간을 받아 DB에 저장"""
    data = request.json
    email = data.get("email")
    send_time_str = data.get("send_time")  # KST로 넘어온 시간

    if not email or not send_time_str:
        return jsonify({"error": "email과 send_time이 필요합니다."}), 400

    try:
        # KST로 넘어온 시간을 UTC로 변환
        send_time = datetime.strptime(send_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST).astimezone(timezone.utc)

        # 발송 기록 저장
        log_email(email=email, send_time=send_time)
        return jsonify({"message": "이메일 발송 기록 저장 완료"}), 200
    except Exception as e:
        app.logger.error(f"Log Email API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/logs", methods=["GET"])
@use_db_session
def view_logs(db):
    """DB의 열람 기록을 조회하여 KST로 변환 후 표시"""
    try:
        logs = db.query(EmailLog).all()
        if not logs:
            return render_template("logs.html", email_status=[], feedback_message="No logs available.")

        viewed_logs = []
        for row in logs:
            viewed_logs.append({
                "timestamp": format_time_to_kst(row.timestamp),  # 열람 시간 UTC -> KST
                "email": row.email,
                "send_time": format_time_to_kst(row.send_time),  # 발송 시간 UTC -> KST
                "ip": row.client_ip,
                "user_agent": row.user_agent
            })

        return render_template("logs.html", email_status=viewed_logs, feedback_message=None)

    except Exception as e:
        app.logger.error(f"로그 조회 오류: {e}")
        return render_template("logs.html", email_status=[], feedback_message="An error occurred while fetching logs."), 500

@app.route("/download_log", methods=["GET"])
@use_db_session
def download_log(db):
    """열람 기록을 CSV 파일로 다운로드"""
    logs = db.query(EmailLog).all()
    if not logs:
        return "No log records to download.", 200

    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(["Timestamp (KST)", "Email", "Send Time (KST)", "Client IP", "User-Agent"])
    for row in logs:
        writer.writerow([
            format_time_to_kst(row.timestamp),
            row.email,
            format_time_to_kst(row.send_time),
            row.client_ip,
            row.user_agent
        ])
    output.seek(0)

    response = make_response(output.read())
    response.headers["Content-Disposition"] = "attachment; filename=email_tracking_log.csv"
    response.headers["Content-Type"] = "text/csv"
    return response

# 서버 초기화 및 실행
def initialize_application():
    init_db()
    get_or_create_pixel_image()

initialize_application()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
