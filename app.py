import os
import requests
from flask import Flask, request, send_file, render_template, jsonify, make_response
from PIL import Image
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, validates
from zoneinfo import ZoneInfo
import logging
import csv
import io

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

# Flask 앱 생성
app = Flask(__name__)

# 한국 표준시(KST) 정의
KST = ZoneInfo("Asia/Seoul")

# 환경 변수 설정
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///email_logs.db")
PIXEL_IMAGE_PATH = os.getenv("PIXEL_IMAGE_PATH", "/tmp/pixel.png")

# SQLAlchemy 초기 설정
engine = create_engine(DATABASE_URL, echo=True, pool_pre_ping=True)
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
    __tablename__ = "email_send_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    send_time = Column(DateTime(timezone=True), nullable=False)  # 발송 시간 (UTC 저장)

    @validates("send_time")
    def validate_send_time(self, key, send_time):
        """발송 시간을 UTC로 변환하여 저장"""
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
    wrapper.__name__ = func.__name__  # 엔드포인트 이름 충돌 방지
    return wrapper

def format_time_to_kst(time_value):
    """UTC 시간을 KST로 변환하고 문자열로 포맷. 잘못된 값은 '발송 기록 없음'으로 대체."""
    try:
        if time_value:
            if isinstance(time_value, str):
                time_value = datetime.fromisoformat(time_value)
            return time_value.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
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

@use_db_session
def clean_invalid_send_time(db):
    """DB에서 잘못된 send_time 값을 정리"""
    invalid_logs = db.query(EmailLog).filter(EmailLog.send_time == "발송 기록 없음").all()
    for log in invalid_logs:
        log.send_time = None
    db.commit()
    app.logger.info(f"잘못된 send_time 데이터 {len(invalid_logs)}건 정리 완료")

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
        timestamp = datetime.now(timezone.utc)  # 현재 열람 시간 (UTC)
        with SessionLocal() as db:
            send_time = db.query(EmailSendLog.send_time).filter(EmailSendLog.email == email).scalar()
            new_log = EmailLog(timestamp=timestamp, email=email, send_time=send_time, client_ip=client_ip, user_agent=user_agent)
            db.add(new_log)
            db.commit()
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
        send_time = datetime.strptime(send_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST).astimezone(timezone.utc)
        with SessionLocal() as db:
            existing_record = db.query(EmailSendLog).filter(EmailSendLog.email == email, EmailSendLog.send_time == send_time).first()
            if not existing_record:
                new_record = EmailSendLog(email=email, send_time=send_time)
                db.add(new_record)
                db.commit()
        return jsonify({"message": "이메일 발송 기록 저장 완료"}), 200
    except Exception as e:
        app.logger.error(f"Log Email API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/logs", methods=["GET"])
@use_db_session
def view_logs(db):
    """DB의 열람 기록을 조회하여 KST로 변환 후 표시"""
    logs = db.query(EmailLog).all()
    viewed_logs = []
    for row in logs:
        viewed_logs.append({
            "timestamp": format_time_to_kst(row.timestamp),
            "email": row.email,
            "send_time": format_time_to_kst(row.send_time),
            "ip": row.client_ip,
            "user_agent": row.user_agent,
        })
    return jsonify(viewed_logs)

@app.route("/download_log", methods=["GET"])
@use_db_session
def download_log(db):
    """열람 기록을 CSV 파일로 다운로드"""
    logs = db.query(EmailLog).all()
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Timestamp (KST)", "Email", "Send Time (KST)", "Client IP", "User-Agent"])
    for row in logs:
        writer.writerow([
            format_time_to_kst(row.timestamp),
            row.email,
            format_time_to_kst(row.send_time),
            row.client_ip,
            row.user_agent,
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
    clean_invalid_send_time()  # 잘못된 데이터 정리

initialize_application()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
