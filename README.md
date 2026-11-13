# AnTumLum Loyalty

Website quản lý khách hàng và tích điểm cho quầy Snack Bar AnTumLum.

## Chạy trên máy tính
1. Cài Python 3.10 trở lên.
2. Mở Terminal tại thư mục dự án.
3. Tạo môi trường và cài thư viện:

   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Chạy website:

   ```bash
   python app.py
   ```

5. Mở http://127.0.0.1:5000

## Tài khoản lần chạy đầu
- Tên đăng nhập: `admin`
- Mật khẩu: `admin12345`

**Bắt buộc đổi mật khẩu mặc định trước khi đưa lên internet.** Đặt biến môi trường `ADMIN_PASSWORD` trước lần chạy đầu tiên để tạo mật khẩu khác; đặt `SECRET_KEY` thành chuỗi bí mật riêng.

## Quy tắc tích điểm mặc định
Mỗi 10.000đ chi tiêu được 1 điểm. Có thể đổi tỷ lệ tại mục Cài đặt. Số điểm được tính theo phần nguyên của hóa đơn (ví dụ 25.000đ = 2 điểm).

## Database
Mặc định SQLite được tạo tự động tại `instance/antumlum.db`, dữ liệu còn nguyên sau khi tắt/mở ứng dụng. Có thể chuyển sang PostgreSQL bằng biến môi trường `DATABASE_URL` khi triển khai.

## Các phần đã có
- Dashboard tổng quan
- Quản lý khách hàng, tìm theo tên/số điện thoại
- Cộng điểm từ hóa đơn và lịch sử giao dịch
- Điều chỉnh điểm thủ công
- Quản lý voucher, đổi điểm lấy voucher và mã voucher
- Cấu hình tỷ lệ tích điểm

## Lưu ý trước khi vận hành thật
Đây là bản MVP khởi đầu. Nên bổ sung HTTPS, sao lưu database tự động, phân quyền nhân viên, xác thực khách hàng khi tra cứu/đổi thưởng, CSRF protection và quy trình xác nhận sử dụng voucher trước khi chạy chính thức.


## Chuẩn bị triển khai Render
- Project đã có `Procfile`, `render.yaml`, Gunicorn và driver PostgreSQL.
- Khi tạo Web Service trên Render, thêm biến `SECRET_KEY` (chuỗi ngẫu nhiên), `ADMIN_PASSWORD` (mật khẩu quản trị mới) và `DATABASE_URL` (connection string PostgreSQL).
- Không commit mật khẩu, secret key hoặc connection string vào Git.
- Với dữ liệu kinh doanh thực tế, chọn PostgreSQL có chính sách lưu trữ/backup phù hợp; không dùng database thử nghiệm tự hết hạn.


## Cổng hội viên và quy trình thanh toán (bản cập nhật)
- QR công khai của shop tại `/join-qr.png` dẫn khách tới trang đăng ký hội viên; có thể in QR này tại quầy. Khách hàng: `/member/register` để đăng ký; `/member/login` để đăng nhập bằng số điện thoại + mật khẩu.
- Trang hội viên `/member`: điểm, QR hội viên cá nhân, lịch sử và đổi voucher. QR chứa token hội viên riêng, không phải QR nhận tiền của shop.
- Nhân viên: `/pos` tạo hóa đơn bằng cách nhập token QR (máy quét QR dạng bàn phím cũng dùng được) hoặc số điện thoại. `/orders` để xác nhận tiền đã nhận.
- Chỉ khi nhân viên xác nhận hóa đơn đang chờ, hệ thống mới cộng điểm; hóa đơn đã xử lý không thể cộng lần hai. Mỗi lần xác nhận tạo một giao dịch điểm gắn mã hóa đơn.
- Thanh toán MoMo/VietQR hiện là xác nhận thủ công. Chưa có kết nối API/webhook MoMo/ngân hàng, do đó không tự đọc biến động số dư.
- `qrcode[pil]` được dùng để sinh QR hội viên.

### Lưu ý nâng cấp database cũ
Ứng dụng tự thêm hai cột `password_hash` và `member_token` vào bảng `customer` cũ khi khởi động. Khách hàng đã có trong database từ phiên bản cũ chưa có mật khẩu; cần quy trình kích hoạt/đặt mật khẩu có xác minh danh tính trước khi cho họ đăng nhập. Không cho phép tự chiếm tài khoản chỉ bằng cách nhập số điện thoại.

### Bảo mật trước khi vận hành thật
Đặt `SECRET_KEY` và `ADMIN_PASSWORD` mạnh; bật HTTPS; sao lưu PostgreSQL; bổ sung CSRF protection, giới hạn đăng nhập sai, quy trình reset mật khẩu có OTP và phân quyền nhân viên. Hiện tại số điện thoại chưa được xác minh bằng OTP.
