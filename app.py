from flask import Flask, request, send_file
from datetime import datetime

app = Flask(__name__)

@app.route('/pixel', methods=['GET'])
def pixel():
    email = request.args.get('email')  # 이메일 주소 받기
    if not email:
        return "이메일 주소가 없습니다!", 400
    
    with open("log.txt", "a") as log_file:
        log_file.write(f"{datetime.now()} - {email}\n")
    
    # 투명한 픽셀 반환
    return send_file('transparent.png', mimetype='image/png')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
