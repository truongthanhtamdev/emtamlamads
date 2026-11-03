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
PORT80=$(ss -ltnp 2>/dev/null | grep -E ':80 ' || true)
CADDY=""
if echo "$PORT80" | grep -q docker-proxy && command -v docker >/dev/null; then
  CADDY=$(docker ps --format '{{.Names}} {{.Image}}' | awk '$2 ~ /^caddy/ {print $1; exit}')
fi

if [ -n "$CADDY" ]; then
  # ---------------------------------------------------------------- CHẾ ĐỘ CADDY (Docker)
  say "Phát hiện Caddy trong Docker ($CADDY) — gắn trang quản trị vào Caddy, không đụng web đang chạy"
  NET=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$CADDY" | awk '{print $1}')
  CONF_SRC=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' "$CADDY")
  if [ -z "$CONF_SRC" ]; then
    DIR_SRC=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/caddy"}}{{.Source}}{{end}}{{end}}' "$CADDY")
    [ -n "$DIR_SRC" ] && CONF_SRC="$DIR_SRC/Caddyfile"
  fi
  if [ -z "$CONF_SRC" ] || [ ! -f "$CONF_SRC" ]; then
    echo "Không tìm thấy file Caddyfile của $CADDY trên máy. Chụp màn hình gửi Claude."; exit 1
  fi
  echo "Mạng Docker: $NET · Caddyfile: $CONF_SRC"

  say "Tải ứng dụng"
  mkdir -p "$APP_DIR/data"
  curl -fsSL "$RAW/app.py" -o "$APP_DIR/app.py.new" && mv "$APP_DIR/app.py.new" "$APP_DIR/app.py"
  chown -R 1000:1000 "$APP_DIR/data"; chmod 700 "$APP_DIR/data"; chmod 644 "$APP_DIR/app.py"

  IMG=python:3.12-alpine
  RUN_ARGS=(--user 1000:1000 -e ETLA_DB=/data/leads.db -e TZ=Asia/Ho_Chi_Minh -v "$APP_DIR/app.py:/app/app.py:ro" -v "$APP_DIR/data:/data")
  say "Khởi tạo cơ sở dữ liệu"
  docker pull -q "$IMG" >/dev/null
  INIT_OUT=$(docker run --rm "${RUN_ARGS[@]}" "$IMG" python /app/app.py --init)

  say "Chạy trang quản trị (container etla-admin, không mở cổng ra ngoài)"
  docker rm -f etla-admin >/dev/null 2>&1 || true
  docker run -d --name etla-admin --restart unless-stopped --network "$NET" --memory 128m \
    "${RUN_ARGS[@]}" -e ETLA_HOST=0.0.0.0 -e ETLA_PORT=$PORT "$IMG" python /app/app.py >/dev/null
  sleep 2
  docker exec etla-admin wget -qO- "http://127.0.0.1:$PORT/healthz" >/dev/null && echo "Ứng dụng đang chạy ✓"

  if grep -q "^$DOMAIN" "$CONF_SRC"; then
    echo "Caddyfile đã có $DOMAIN — giữ nguyên."
  else
    say "Thêm $DOMAIN vào Caddyfile (đã sao lưu)"
    BACKUP="$CONF_SRC.bak-$(date +%Y%m%d-%H%M%S)"
    cp "$CONF_SRC" "$BACKUP"
    printf '\n%s {\n\treverse_proxy etla-admin:%s\n}\n' "$DOMAIN" "$PORT" >> "$CONF_SRC"   # nối thêm, giữ nguyên file gốc
    if docker exec "$CADDY" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 \
       && docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
      echo "Caddy đã nạp cấu hình mới ✓ (bản sao lưu: $BACKUP)"
    else
      cat "$BACKUP" > "$CONF_SRC"
      docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || true
      echo "Caddy báo lỗi cấu hình — ĐÃ TRẢ LẠI CADDYFILE CŨ, web đang chạy không bị ảnh hưởng. Chụp màn hình gửi Claude."
      exit 1
    fi
  fi

  SERVER_IP=$(curl -fsS https://api.ipify.org || true)
  DNS_IP=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)
  echo
  echo "=============================================================="
  echo " XONG! Trang quản trị: https://$DOMAIN"
  echo "$INIT_OUT" | grep -q "MAT KHAU" && echo " $INIT_OUT   <-- LƯU LẠI, chỉ hiện 1 lần"
  if [ "$SERVER_IP" != "$DNS_IP" ]; then
    echo " Lưu ý: $DOMAIN chưa trỏ về VPS (đang: ${DNS_IP:-chưa có}). Thêm bản ghi A: admin -> $SERVER_IP."
    echo " Caddy tự bật https khi tên miền trỏ đúng — không cần chạy lại."
  fi
  echo " Quên mật khẩu: docker exec -u 1000 etla-admin python /app/app.py --reset-password"
  echo "=============================================================="
  exit 0
fi

if [ -n "$PORT80" ] && echo "$PORT80" | grep -vq nginx; then
  echo "CỔNG 80 ĐANG BỊ CHƯƠNG TRÌNH KHÁC DÙNG (không phải nginx):"
  echo "$PORT80"
  echo "Dừng lại để không làm hỏng web khác trên VPS. Chụp màn hình này gửi Claude."
  exit 1
fi

# ---------------------------------------------------------------- CHẾ ĐỘ NGINX (VPS trống)
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
