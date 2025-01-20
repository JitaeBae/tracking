from flask import Flask, request, send_file
from datetime import datetime

app = Flask(__name__)

# 트래킹 픽셀 엔드포인트
@app.route('/pixel', methods=['GET'])
def pixel():
    email = request.args.get('email')
    if not email:
        return "이메일 주소가 없습니다!", 400

    print(f"{datetime.now()} - {email} - 이메일 열림 확인")
    return send_file('transparent.png', mimetype='image/png')

# 디버깅용 기본 경로
@app.route('/')
def home():
    try:
        # Flask 앱 실행 상태 확인용
        return "정상 실행: Flask 서버가 정상적으로 작동 중입니다!", 200
    except Exception as e:
        print(f"서버 오류 발생: {e}")  # Logs에 출력
        return "서버 오류 발생!", 500

# 에러 핸들러 추가
@app.errorhandler(Exception)
def handle_exception(e):
    print(f"예외 처리: {e}")  # Logs에 에러 출력
    return "서버 오류가 발생했습니다. 관리자에게 문의하세요.", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
