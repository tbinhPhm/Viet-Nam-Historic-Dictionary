## Avatar Upload Server (Dev)

Mục tiêu: nhận file avatar từ app, upload lên Firebase Storage, trả về `avatar_url` và update vào Firestore `users`.

### Cài đặt

`pip install -r server/requirements.txt`

### Chạy

`python server/avatar_upload_server.py`

Mặc định chạy tại `http://127.0.0.1:5055`.

### Gọi từ app

Trong PowerShell:

`$env:USE_FIREBASE="1"`

`$env:AVATAR_UPLOAD_ENDPOINT="http://127.0.0.1:5055/upload-avatar"`

`$env:IMGBB_API_KEY="YOUR_IMGBB_KEY"`

### API

`POST /upload-avatar`

Form-data:
- `username`: string
- `file`: image file

Response:
- `{ "avatar_url": "https://..." }`
