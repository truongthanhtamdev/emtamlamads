#!/usr/bin/env bash
# Cài trang quản trị khách đặt lịch Em Tâm Làm Ads lên VPS (Ubuntu/Debian).
#
#   curl -fsSL https://raw.githubusercontent.com/truongthanhtamdev/emtamlamads/main/server/install.sh | sudo bash
#
# Chạy lại lệnh này bất cứ lúc nào để cập nhật phiên bản mới — dữ liệu khách được giữ nguyên.
set -euo pipefail

DOMAIN="${DOMAIN:-admin.emtamlamads.com}"
APP_DIR=/opt/emtamlamads-admin
RAW=https://raw.githubusercontent.com/truongthanhtamdev/emtamlamads/main/server
PORT=8787

say(){ printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "Hãy chạy bằng quyền root (sudo)."; exit 1; }

say "Kiểm tra cổng 80"
if ss -ltnp 2>/dev/null | grep -E ':80 ' | grep -vq nginx; then
  echo "CỔNG 80 ĐANG BỊ CHƯƠNG TRÌNH KHÁC DÙNG (không phải nginx):"
  ss -ltnp | grep -E ':80 '
  echo "Dừng lại để không làm hỏng web khác trên VPS. Chụp màn hình này gửi Claude."
  exit 1
fi

say "Cài python3, nginx, certbot"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 nginx certbot python3-certbot-nginx curl

say "Tải ứng dụng"
id -u etla >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin etla
mkdir -p "$APP_DIR/data"
curl -fsSL "$RAW/app.py" -o "$APP_DIR/app.py.new" && mv "$APP_DIR/app.py.new" "$APP_DIR/app.py"
chown -R etla:etla "$APP_DIR"
chmod 700 "$APP_DIR/data"

say "Khởi tạo cơ sở dữ liệu"
INIT_OUT=$(sudo -u etla env ETLA_DB="$APP_DIR/data/leads.db" python3 "$APP_DIR/app.py" --init)

say "Tạo dịch vụ chạy nền"
cat > /etc/systemd/system/emtamlamads-admin.service <<EOF
[Unit]
Description=Em Tam Lam Ads - quan tri khach dat lich
After=network.target

[Service]
User=etla
Group=etla
Environment=ETLA_DB=$APP_DIR/data/leads.db
Environment=ETLA_HOST=127.0.0.1
Environment=ETLA_PORT=$PORT
Environment=TZ=Asia/Ho_Chi_Minh
ExecStart=/usr/bin/python3 $APP_DIR/app.py
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR/data
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now emtamlamads-admin
systemctl restart emtamlamads-admin

say "Cấu hình nginx cho $DOMAIN"
cat > /etc/nginx/sites-available/emtamlamads-admin <<EOF
server {
  listen 80;
  server_name $DOMAIN;
  client_max_body_size 64k;
  location / {
    proxy_pass http://127.0.0.1:$PORT;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }
}
EOF
ln -sf /etc/nginx/sites-available/emtamlamads-admin /etc/nginx/sites-enabled/emtamlamads-admin
command -v ufw >/dev/null && ufw status | grep -q active && ufw allow 80,443/tcp || true
nginx -t && systemctl reload nginx

say "Bật https"
SERVER_IP=$(curl -fsS https://api.ipify.org || true)
DNS_IP=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)
if [ -n "$SERVER_IP" ] && [ "$SERVER_IP" = "$DNS_IP" ]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || echo "Chưa bật được https — chạy lại lệnh cài sau ít phút."
  HTTPS_OK=1
else
  echo "Tên miền $DOMAIN chưa trỏ về VPS này (đang trỏ: ${DNS_IP:-chưa có}, IP VPS: ${SERVER_IP:-?})."
  echo "Thêm bản ghi A: admin -> ${SERVER_IP:-IP VPS}, đợi 5-30 phút rồi chạy lại đúng lệnh cài này để bật https."
  HTTPS_OK=0
fi

sleep 1
curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null && echo "Ứng dụng đang chạy ✓"

echo
echo "=============================================================="
echo " XONG! Trang quản trị: https://$DOMAIN"
echo "$INIT_OUT" | grep -q "MAT KHAU" && echo " $INIT_OUT   <-- LƯU LẠI, chỉ hiện 1 lần"
[ "$HTTPS_OK" = 1 ] || echo " (https sẽ có sau khi trỏ tên miền và chạy lại lệnh cài)"
echo " Quên mật khẩu: sudo -u etla env ETLA_DB=$APP_DIR/data/leads.db python3 $APP_DIR/app.py --reset-password"
echo "=============================================================="
