import os
import requests
from flask import Flask, request, send_file, render_template, jsonify, redirect, url_for, make_response
from PIL import Image
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, Column, Integer, String, DateTime, and_
from sqlalchemy.orm import declarative_base, sessionmaker
import logging

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logging.getLogger(__name__).setLevel(logging.DEBUG)

# Flask 앱 생성
app = Flask(__name__)

# 한국 표준시(KST) 정의
KST = ZoneInfo('Asia/Seoul')

# 환경 변수
DATABASE_URL = os.getenv("DATABASE_URL")
PIXEL_IMAGE_PATH = os.getenv("PIXEL_IMAGE_PATH", "/tmp/pixel.png")

# SQLAlchemy 초기화
engine = create_engine(DATABASE_URL, echo=True, connect_args={"sslmode": "require"})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# DB 테이블 정의
class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)  # 열람 시간 (UTC)
    email = Column(String, nullable=False)
    send_time = Column(DateTime, nullable=True)  # 발송 시간 (UTC)
    client_ip = Column(String, nullable=False)
    user_agent = Column(String, nullable=False)

class EmailSendLog(Base):
    __tablename__ = 'email_send_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    send_time = Column(DateTime, nullable=False)  # 발송 시간 (UTC)

# DB 초기화
def init_db():
    Base.metadata.create_all(bind=engine)
    app.logger.info("DB 테이블 생성 완료.")

# 픽셀 이미지 생성
def create_pixel_image():
    if not os.path.exists(PIXEL_IMAGE_PATH):
        pixel_image = Image.new("RGB", (1, 1), (255, 255, 255))
        pixel_image.save(PIXEL_IMAGE_PATH)
        app.logger.info("픽셀 이미지 생성 완료.")
    return PIXEL_IMAGE_PATH

# 이메일 발송 시간 조회
def get_email_send_time(email):
    with SessionLocal() as db:
        record = db.query(EmailSendLog).filter(EmailSendLog.email == email).first()
        return record.send_time if record else None

# 라우트 정의
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "message": "이메일 트래킹 시스템 실행 중"}), 200

@app.route("/track", methods=["GET"])
def track_email():
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    email = request.args.get("email")

    if not email:
        return "이메일 파라미터가 없습니다.", 400

    send_time = get_email_send_time(email)
    timestamp = datetime.now(timezone.utc)  # UTC 타임스탬프

    with SessionLocal() as db:
        # 중복 기록 방지
        existing_log = db.query(EmailLog).filter(
            and_(
                EmailLog.email == email,
                EmailLog.send_time == send_time,
                EmailLog.client_ip == client_ip
            )
        ).first()
        if existing_log:
            app.logger.info(f"중복 기록 방지: {email}, IP: {client_ip}")
            return send_file(create_pixel_image(), mimetype="image/png")

        # 새로운 로그 추가
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
            app.logger.info(f"이메일 열람 기록 저장: {email}, 발송 시간: {send_time}, IP: {client_ip}")
        except Exception as e:
            db.rollback()
            app.logger.error(f"열람 기록 저장 오류: {e}")
            return "열람 기록 저장 오류", 500

    return send_file(create_pixel_image(), mimetype="image/png")

@app.route("/logs", methods=["GET", "POST"])
def view_logs():
    with SessionLocal() as db:
        try:
            if request.method == "POST":
                db.query(EmailLog).delete()
                db.commit()
                app.logger.info("로그 데이터 초기화 완료.")
                return redirect(url_for("view_logs"))

            logs = db.query(EmailLog).all()
            if not logs:
                return render_template("logs.html", email_status=[], feedback_message="No logs available.")

            viewed_logs = []
            for row in logs:
                viewed_logs.append({
                    "timestamp": row.timestamp.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S"),
                    "email": row.email,
                    "send_time": (row.send_time.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
                                  if row.send_time else "발송 기록 없음"),
                    "ip": row.client_ip,
                    "user_agent": row.user_agent
                })

            return render_template("logs.html", email_status=viewed_logs, feedback_message=None)
        except Exception as e:
            app.logger.error(f"로그 조회 오류: {e}")
            return render_template("logs.html", email_status=[], feedback_message="An error occurred."), 500

@app.route("/log-email", methods=["POST"])
def log_email():
    data = request.json
    email = data.get("email")
    send_time_str = data.get("send_time")

    if not email or not send_time_str:
        return jsonify({"error": "email과 send_time이 필요합니다."}), 400

    with SessionLocal() as db:
        try:
            send_time = datetime.fromisoformat(send_time_str).replace(tzinfo=KST).astimezone(timezone.utc)
            new_record = EmailSendLog(email=email, send_time=send_time)
            db.add(new_record)
            db.commit()
            return jsonify({"message": "이메일 발송 기록 저장 완료"}), 200
        except Exception as e:
            db.rollback()
            app.logger.error(f"이메일 발송 기록 저장 오류: {e}")
            return jsonify({"error": str(e)}), 500

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({"error": "An internal server error occurred"}), 500

# 서버 초기화
def initialize_application():
    init_db()
    create_pixel_image()

initialize_application()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
