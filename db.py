# db.py
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# 1) 환경변수에서 DB 연결 URL 가져오기
DATABASE_URL = os.getenv("DATABASE_URL")

# 2) 엔진 생성
# echo=False → 쿼리 로그를 표시하지 않음 (debug 용도로 echo=True 가능)
engine = create_engine(DATABASE_URL, echo=False)

# 3) 세션 팩토리
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4) 모델 베이스
Base = declarative_base()

# 5) 실제 로그를 저장할 테이블 정의
class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    email = Column(String)
    client_ip = Column(String)
    user_agent = Column(String)

# 6) 테이블 생성 함수
def init_db():
    Base.metadata.create_all(bind=engine)
