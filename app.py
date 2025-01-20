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
    return "Flask 앱이 정상적으로 실행 중입니다!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
