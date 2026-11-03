/**
 * Nhận đăng ký từ các landing page của emtamlamads.com (/quaychupdung, /quangcao)
 * và ghi vào Google Sheet.
 *
 * Cách cài (một lần, khoảng 3 phút):
 *  1. Mở Google Sheet "Đăng ký học thử – emtamlamads.com" → Tiện ích mở rộng → Apps Script.
 *  2. Xoá hết code có sẵn, dán toàn bộ file này vào, bấm Lưu.
 *  3. Bấm Triển khai → Tùy chọn triển khai mới → loại "Ứng dụng web":
 *       - Thực thi dưới dạng: Tôi
 *       - Người có quyền truy cập: Bất kỳ ai
 *     Bấm Triển khai, cấp quyền, rồi sao chép "URL ứng dụng web" (…/exec).
 *  4. Gửi URL đó cho Claude (hoặc dán vào LEAD_ENDPOINT trong quaychupdung/index.html).
 *
 * Mỗi đăng ký mới: thêm 1 dòng vào sheet + gửi email báo cho chủ sheet.
 */
var NOTIFY_BY_EMAIL = true;
var HEADERS = ['Thời gian gửi', 'Loại', 'Tên', 'SĐT / Zalo', 'Email', 'Fanpage', 'Ngày hẹn', 'Khung giờ (giờ VN)',
               'Ngân sách ads/tháng', 'Mục tiêu', 'Ghi chú', 'Trang', 'Nguồn quảng cáo', 'Trạng thái'];

function doPost(e) {
  var p = (e && e.parameter) || {};
  // Bẫy spam: ô "website" bị ẩn trên form, người thật không điền.
  if (p.website) return json_({ ok: true });

  var name = clean_(p.name), phone = clean_(p.phone), email = clean_(p.email);
  if (!name || (!phone && !email)) return json_({ ok: false, error: 'missing' });

  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
    var head = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
    if (head.join('|') !== HEADERS.join('|')) {
      sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
      sheet.setFrozenRows(1);
    }
    sheet.appendRow([
      new Date(), clean_(p.kind), name, phone ? "'" + phone : '', email, clean_(p.fanpage), clean_(p.date), clean_(p.times),
      clean_(p.budget), clean_(p.goal), clean_(p.note), clean_(p.page), clean_(p.utm), 'Mới'
    ]);
  } finally {
    lock.releaseLock();
  }

  if (NOTIFY_BY_EMAIL) {
    try {
      MailApp.sendEmail(Session.getEffectiveUser().getEmail(),
        'Khách mới (' + clean_(p.kind) + '): ' + name + ' – ' + (phone || email),
        'Loại: ' + clean_(p.kind) + '\nTên: ' + name + '\nSĐT/Zalo: ' + phone + '\nEmail: ' + email +
        '\nNgày hẹn: ' + clean_(p.date) + '\nKhung giờ (giờ VN): ' + clean_(p.times) + '\nFanpage: ' + clean_(p.fanpage) +
        '\nNgân sách ads/tháng: ' + clean_(p.budget) + '\nMục tiêu: ' + clean_(p.goal) +
        '\nGhi chú: ' + clean_(p.note) + '\nTrang: ' + clean_(p.page) + '\nNguồn: ' + clean_(p.utm) +
        '\n\nMở sheet: ' + SpreadsheetApp.getActiveSpreadsheet().getUrl());
    } catch (err) {}
  }
  return json_({ ok: true });
}

function doGet() { return json_({ ok: true, service: 'emtamlamads-dang-ky' }); }

function clean_(v) { return String(v || '').replace(/^[=+\-@]/, "'$&").slice(0, 1000).trim(); }
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
