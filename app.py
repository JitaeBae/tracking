import os
import requests
from flask import Flask, request, send_file, render_template, jsonify, redirect, url_for, make_response
from PIL import Image
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========= SQLAlchemy & DB 연결 설정 =========
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.orm import validates
from sqlalchemy import event  # SQLAlchemy 이벤트 모듈
from sqlalchemy.orm import Session
import logging

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logging.getLogger(__name__).setLevel(logging.DEBUG)

# Flask 앱 생성
app = Flask(__name__)

# 한국 표준시(KST) 정의
KST = ZoneInfo('Asia/Seoul')

# ------------------------
# 1. 환경 변수/타임존/기타
# ------------------------
DATABASE_URL = os.getenv("DATABASE_URL")  # 예: "postgresql://user:pass@host:port/db"

# (과거 CSV 파일 이름이었지만, DB 사용으로 대체)
LOG_FILE = os.getenv("LOG_FILE_PATH", "email_tracking_log.csv")
SEND_LOG_FILE = os.getenv("SEND_LOG_FILE_PATH", "email_send_log.csv")

# -----------------------
# 2. SQLAlchemy 초기 설정
# -----------------------

from sqlalchemy.pool import NullPool

# SQLAlchemy 엔진 생성
engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQLALCHEMY_ECHO", "False").lower() == "true",  # 환경 변수로 echo 제어
    pool_size=int(os.getenv("SQLALCHEMY_POOL_SIZE", 10)),          # 기본 풀 크기를 10으로 설정
    max_overflow=int(os.getenv("SQLALCHEMY_MAX_OVERFLOW", 5)),     # 기본 초과 연결 개수
    pool_recycle=int(os.getenv("SQLALCHEMY_POOL_RECYCLE", 1800)),  # 기본 재활용 시간(초)
    pool_pre_ping=True,                                           # 연결 유효성 검사
    poolclass=NullPool if os.getenv("SQLALCHEMY_USE_POOL", "True").lower() == "false" else None,  # 연결 풀 비활성화 옵션
    connect_args={
        "sslmode": os.getenv("SQLALCHEMY_SSLMODE", "require"),    # SSL 모드 설정
        "keepalives": 1,
        "keepalives_idle": int(os.getenv("SQLALCHEMY_KEEPALIVES_IDLE", 30)),
        "keepalives_interval": int(os.getenv("SQLALCHEMY_KEEPALIVES_INTERVAL", 10)),
        "keepalives_count": int(os.getenv("SQLALCHEMY_KEEPALIVES_COUNT", 5)),
    },
)

# 세션 생성
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# 세션 이벤트 등록
@event.listens_for(Session, "after_begin")
def after_begin(session, transaction, connection):
    session.expire_all()  # 세션 캐시 무효화
# 베이스 클래스 정의
Base = declarative_base()


# -----------------------------
# 3. DB 테이블(ORM 모델) 정의
# -----------------------------
class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    email = Column(String, nullable=False)
    send_time = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    client_ip = Column(String)
    user_agent = Column(String)

class EmailSendLog(Base):
    __tablename__ = 'email_send_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    send_time = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    client_ip = Column(String, nullable=False)
    user_agent = Column(String, nullable=False)

@validates("send_time")
def validate_send_time(self, key, send_time):
    logger = logging.getLogger(__name__)

    # 문자열인 경우 처리
    if isinstance(send_time, str):
        try:
            # 문자열을 datetime으로 변환
            send_time = datetime.strptime(send_time, "%Y-%m-%d %H:%M:%S")
            send_time = send_time.replace(tzinfo=KST)  # KST로 설정
            send_time = send_time.astimezone(timezone.utc)  # UTC로 변환
            logger.debug(f"Converted send_time to UTC: {send_time}")
        except ValueError:
            logger.error("send_time must be in 'YYYY-MM-DD HH:MM:SS' format.")
            raise ValueError("send_time must be in 'YYYY-MM-DD HH:MM:SS' format.")

    # datetime 객체인 경우 처리
    elif isinstance(send_time, datetime):
        if send_time.tzinfo is None:  # 시간대 정보가 없으면 KST로 설정
            send_time = send_time.replace(tzinfo=KST)
            send_time = send_time.astimezone(timezone.utc)
            logger.debug(f"Applied KST timezone and converted to UTC: {send_time}")

    # 다른 데이터 타입인 경우 예외 처리
    else:
        logger.error(f"Invalid type for send_time: {type(send_time)}")
        raise TypeError("send_time must be a string in 'YYYY-MM-DD HH:MM:SS' format or a datetime object.")

    # 현재 UTC 시간과 비교
    current_time = datetime.now(timezone.utc)
    logger.debug(f"Current time (UTC): {current_time}, send_time: {send_time}")

    if send_time > current_time:
        logger.error("send_time cannot be in the future.")
        raise ValueError("send_time cannot be in the future.")

    return send_time


# ---------------------
# 4. DB 초기화 함수
# ---------------------
def init_db():
    Base.metadata.create_all(bind=engine)
    app.logger.info("DB 테이블 생성(또는 이미 존재).")

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
            app.logger.info("픽셀 이미지 생성 완료")
        except Exception as e:
            app.logger.error(f"픽셀 이미지 생성 오류: {e}")
    return pixel_path

def get_email_send_time(email):
    """DB에서 email에 해당하는 발송 시간을 찾거나, 없으면 '발송 기록 없음'"""
    with SessionLocal() as db:
        db.expire_all()

        # 방법 A) id가 높은 것이 최신이라고 가정할 경우
        record = (
            db.query(EmailSendLog)
            .filter(EmailSendLog.email == email)
            .order_by(EmailSendLog.id.desc())
            .first()
        )
        
        # 방법 B) send_time이 가장 최근인 레코드
        # record = (
        #    db.query(EmailSendLog)
        #    .filter(EmailSendLog.email == email)
        #    .order_by(EmailSendLog.send_time.desc())
        #    .first()
        #)

        if record:
            return record.send_time
        else:
            return "발송 기록 없음"

def log_email_send(email):
    """이메일 발송 기록 저장 (과거 CSV -> DB)"""
    with SessionLocal() as db:
        try:
            send_time = datetime.now(timezone.utc).isoformat()
            new_record = EmailSendLog(email=email, send_time=send_time)
            db.add(new_record)
            db.commit()
            app.logger.info(f"이메일 발송 기록 저장: {email}, 발송 시간: {send_time}")
        except Exception as e:
            db.rollback()
            app.logger.error(f"이메일 발송 기록 오류: {e}")

# -----------------
# 6. 라우트 정의
# -----------------

@app.route("/", methods=["GET"])
def home():
    """서버 상태 확인"""
    app.logger.info("홈 라우트에 접근했습니다.")
    return jsonify({"status": "running", "message": "이메일 트래킹 시스템이 실행 중입니다."}), 200

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

@app.route("/track", methods=["GET"])
def track_email():
    """이메일 열람 트래킹 (DB에 저장)"""
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    email = request.args.get("email")

    if not email:
        app.logger.warning("이메일 파라미터가 없습니다.")
        return "이메일 파라미터가 없습니다.", 400

    # UTC 타임스탬프
    timestamp = datetime.now(timezone.utc)
        
    # 이메일 발송 시간 조회
    send_time = get_email_send_time(email)

    # DB에 기록
    with SessionLocal() as db:
        db.expire_all()
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
            app.logger.info(f"Tracking email: {email}, Send Time: {send_time}, IP: {client_ip}")
        except Exception as e:
            db.rollback()
            app.logger.error(f"열람 기록 저장 오류: {e}")
            return "열람 기록 저장 오류", 500

    # 픽셀 이미지 반환
    return send_file(create_pixel_image(), mimetype="image/png")

@app.route("/logs", methods=["GET", "POST"])
def view_logs():
    """열람 기록 보기 (GET) / 초기화 (POST)"""
    with SessionLocal() as db:
        db.expire_all()
        try:
            if request.method == "POST":
                # 전체 로그 삭제
                db.query(EmailLog).delete()
                db.commit()
                app.logger.info("로그 데이터 초기화 완료.")
                return redirect(url_for("view_logs"))

            # GET: 로그 조회
            logs = db.query(EmailLog).all()
            if not logs:
                return render_template("logs.html", email_status=[], feedback_message="No logs available.")

            viewed_logs = []
            
            for row in logs:
                # send_time을 ISO 형식으로 변환 가능 여부 확인
                try:
                    if row.send_time and row.send_time != "발송 기록 없음":
                        if isinstance(row.send_time, datetime):
                            # 이미 datetime 객체인 경우
                            send_time_kst = row.send_time.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            # 문자열인 경우 datetime 객체로 변환
                            send_time_kst = datetime.fromisoformat(row.send_time).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        send_time_kst = "발송 기록 없음"
                except Exception as e:
                    app.logger.warning(f"Invalid send_time format for email '{row.email}': {row.send_time}. Error: {e}")
                    send_time_kst = "발송 기록 없음"
            
                viewed_logs.append({
                    "timestamp": row.timestamp.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S"),  # UTC -> KST 변환
                    "email": row.email,
                    "send_time": send_time_kst,
                    "ip": row.client_ip,
                    "user_agent": row.user_agent
                })


            return render_template("logs.html", email_status=viewed_logs, feedback_message=None)

        except Exception as e:
            app.logger.error(f"로그 조회 오류: {e}")
            return render_template("logs.html", email_status=[], feedback_message="An error occurred while fetching logs."), 500



@app.route("/download_log", methods=["GET"])
def download_log():
    """트래킹 로그를 CSV 파일 형태로 다운로드 (DB -> 메모리 -> 응답)"""
    import csv
    import io

    with SessionLocal() as db:
        db.expire_all()
        try:
            logs = db.query(EmailLog).all()
            if not logs:
                app.logger.info("다운로드할 로그 레코드가 없습니다.")
                return "No log records to download.", 200

                # 메모리에 CSV 작성
                output = io.StringIO()
                writer = csv.writer(output, lineterminator='\n')
                
                # 헤더 작성
                writer.writerow(["Timestamp (KST)", "Email", "Send Time (KST)", "Client IP", "User-Agent"])
                
                # 데이터 작성
                for row in logs:
                    try:
                        # send_time 타입 확인 및 변환
                        if row.send_time:
                            if isinstance(row.send_time, datetime):
                                send_time_kst = row.send_time.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                send_time_kst = datetime.fromisoformat(row.send_time).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            send_time_kst = "N/A"
                    except Exception as e:
                        app.logger.warning(f"Invalid send_time format for email '{row.email}': {row.send_time}. Error: {e}")
                        send_time_kst = "N/A"
                
                    # 각 행 작성
                    writer.writerow([
                        row.timestamp.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S"),  # Timestamp 변환
                        row.email,  # Email
                        send_time_kst,  # Send Time (KST)
                        row.client_ip,  # Client IP
                        row.user_agent  # User-Agent
                    ])
                
                # 메모리 스트림의 위치를 처음으로 이동
                output.seek(0)


            # Flask 응답으로 CSV 파일 전송
            response = make_response(output.read())
            response.headers["Content-Disposition"] = "attachment; filename=email_tracking_log.csv"
            response.headers["Content-Type"] = "text/csv"
            app.logger.info("CSV 파일 다운로드 성공.")
            return response
        except Exception as e:
            app.logger.error(f"CSV 다운로드 오류: {e}")
            return "CSV 다운로드 오류", 500


@app.route("/log-email", methods=["POST"])
def log_email():
    """이메일 발송 기록 저장"""
    data = request.json
    email = data.get("email")
    send_time_str = data.get("send_time")  # 클라이언트에서 전달된 send_time

    app.logger.debug(f"Received email: {email}, send_time_str: {send_time_str}")

    # 필수 필드 확인
    if not email or not send_time_str:
        app.logger.warning("Missing email or send_time_str")
        return jsonify({"error": "email과 send_time이 필요합니다."}), 400

    # 발송 기록 저장
    with SessionLocal() as db:
        try:
            new_record = EmailSendLog(email=email, send_time=send_time_str)
            db.add(new_record)
            db.commit()
            app.logger.info("이메일 발송 기록 저장 완료.")
            return jsonify({"message": "이메일 발송 기록이 저장되었습니다."}), 200
        except Exception as e:
            db.rollback()
            app.logger.error(f"이메일 발송 기록 저장 오류: {e}")
            return jsonify({"error": str(e)}), 500



@app.route("/process-requests", methods=["POST"])
def process_requests():
    """
    1,000개의 요청을 10개씩 분할하여 처리
    요청 데이터는 JSON 배열 형식으로 전달됩니다.
    """
    data = request.json
    if not isinstance(data, list) or len(data) != 1000:
        return jsonify({"error": "1,000개의 요청 데이터를 JSON 배열로 전달해야 합니다."}), 400

    # 최대 동시 처리 개수 및 배치 크기
    max_workers = 10
    batch_size = 10

    # 요청 데이터 분할
    batches = [data[i:i + batch_size] for i in range(0, len(data), batch_size)]

    def handle_request(request_data):
        """단일 요청 처리"""
        try:
            email = request_data.get("email")
            send_time_str = request_data.get("send_time")
            if not email or not send_time_str:
                raise ValueError("email과 send_time 필드는 필수입니다.")

            # 발송 기록 저장
            log_to_db(
                EmailSendLog,
                email=email,
                send_time=send_time_str,
                client_ip="127.0.0.1",  # 예시 IP (수정 가능)
                user_agent="BatchProcessor/1.0",  # 예시 User-Agent
            )
            return {"status": "success", "email": email}
        except Exception as e:
            return {"status": "error", "email": request_data.get("email", "unknown"), "error": str(e)}

    results = []

    # ThreadPoolExecutor를 사용하여 병렬 처리
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for batch in batches:
            futures = [executor.submit(handle_request, request) for request in batch]

            # 현재 배치의 결과를 기다림
            for future in as_completed(futures):
                results.append(future.result())

    # 처리 결과 반환
    success_count = sum(1 for result in results if result["status"] == "success")
    error_count = len(results) - success_count

    return jsonify({
        "message": f"{success_count}개의 요청이 성공적으로 처리되었습니다.",
        "errors": [result for result in results if result["status"] == "error"]
    }), 200


@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error(f"Server error: {e}")
    return jsonify({"error": "An internal server error occurred"}), 500

# ---------------------
# 7. 핑 & 스케줄
# ---------------------
def ping_server():
    """서버 상태를 확인하는 핑 기능"""
    server_url = os.getenv("SERVER_URL", "https://tracking-g39r.onrender.com")
    try:
        app.logger.debug(f"핑 전송 시도 중: {server_url}")
        response = requests.get(server_url)
        if response.status_code == 200:
            app.logger.info(f"핑 전송 성공: {response.status_code}")
        else:
            app.logger.warning(f"핑 전송 실패: {response.status_code}")
    except Exception as e:
        app.logger.error(f"핑 전송 오류: {e}")

def schedule_tasks():
    """APScheduler로 주기적인 작업을 설정"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(ping_server, 'interval', minutes=10)  # 10분마다 ping
    scheduler.start()
    app.logger.info("APScheduler를 통해 작업이 스케줄링되었습니다.")
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
    
initialize_application()
# -------------------
# 9. 앱 실행 (로컬)
# -------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
