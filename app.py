from flask import Flask, request, jsonify
import psycopg2
import logging
import os

app = Flask(__name__)

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)

# PostgreSQL 연결 정보 (환경 변수로 관리)
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'your_host'),         # PostgreSQL 호스트 주소
    'port': os.getenv('DB_PORT', '5432'),             # PostgreSQL 포트 (기본값: 5432)
    'database': os.getenv('DB_NAME', 'your_db_name'), # 데이터베이스 이름
    'user': os.getenv('DB_USER', 'your_username'),    # 사용자 이름
    'password': os.getenv('DB_PASSWORD', 'your_password') # 비밀번호
}

# 데이터베이스 연결 함수
def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logging.info("Database connection established successfully.")
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        raise

# /logs 엔드포인트: 로그 조회
@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 로그 데이터를 가져오는 SQL 쿼리
        query = "SELECT id, email, opened_at FROM email_logs ORDER BY opened_at DESC LIMIT 100;"
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # 결과를 JSON 형태로 변환
        columns = [desc[0] for desc in cursor.description]
        data = [dict(zip(columns, row)) for row in rows]
        
        return jsonify(data)  # JSON 형식으로 반환
    
    except psycopg2.Error as e:
        logging.error(f"SQL Error: {e}")
        return jsonify({'error': 'Database query failed', 'details': str(e)}), 500
    
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# /pixel 엔드포인트: 이메일 추적 로그 기록
@app.route('/pixel', methods=['GET'])
def pixel():
    try:
        email = request.args.get('email')
        if not email:
            return jsonify({'error': 'Email parameter is missing'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 이메일을 DB에 기록하는 SQL 쿼리
        query = "INSERT INTO email_logs (email, opened_at) VALUES (%s, NOW());"
        cursor.execute(query, (email,))
        conn.commit()
        
        return "Pixel logged successfully", 200
    
    except psycopg2.Error as e:
        logging.error(f"Database error during pixel logging: {e}")
        return jsonify({'error': 'Database operation failed', 'details': str(e)}), 500
    
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# 기본 라우트: 서버 상태 확인
@app.route('/')
def index():
    return "Server is running."

if __name__ == '__main__':
    # Flask 애플리케이션 실행
    app.run(host='0.0.0.0', port=5000)
