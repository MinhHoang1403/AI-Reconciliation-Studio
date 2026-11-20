---
name: AI Reconciliation Studio
description: Đối soát dữ liệu bán hàng có AI hỗ trợ, in kết quả với kỷ luật của một tờ tiền polymer
colors:
  polymer-ground: "#f5f8fc"
  surface: "#ffffff"
  ink: "#14233a"
  ink-soft: "#3a4d66"
  blue-20k: "#2a6fc9"
  blue-deep: "#2160b0"
  blue-ink: "#1f5fae"
  blue-tint: "#e4eefb"
  blue-tint-strong: "#d2e2f7"
  on-blue: "#ffffff"
  rail-ink: "#2f4a6e"
  rail-line: "#cfdcef"
  attention-200k: "#b54a26"
  attention-tint: "#f6e4dc"
  matched-100k: "#3a7236"
  matched-tint: "#e1ecdd"
  active-50k: "#7a3e7d"
  active-tint: "#efe2ee"
  line: "#c8d4e3"
  line-soft: "#e0e7f1"
typography:
  display:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "clamp(28px, 3vw, 36px)"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
    fontFeature: "tnum"
  label:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  small: "8px"
  card: "12px"
  pill: "999px"
spacing:
  tight: "8px"
  group: "16px"
  section: "28px"
  page: "40px"
components:
  button-primary:
    backgroundColor: "{colors.blue-20k}"
    textColor: "{colors.on-blue}"
    rounded: "{rounded.small}"
    padding: "0 20px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.blue-deep}"
  nav-rail:
    backgroundColor: "{colors.blue-tint}"
    textColor: "{colors.rail-ink}"
    width: "260px"
  nav-link-current:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.blue-ink}"
    rounded: "{rounded.small}"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "24px"
  next-step-band:
    backgroundColor: "{colors.blue-tint}"
    rounded: "{rounded.card}"
    padding: "24px 28px"
  step-current-chip:
    backgroundColor: "{colors.active-tint}"
    textColor: "{colors.active-50k}"
    rounded: "{rounded.pill}"
---

# Design System: AI Reconciliation Studio

## Overview

**Creative North Star: "Tờ tiền polymer"**

Kết quả đối soát là chuyện tiền bạc, nên giao diện mượn kỷ luật của thứ mọi người Việt đều tin là thật: tờ tiền polymer. Màu theo mệnh giá mang nghĩa cố định, chữ số in theo cột thẳng hàng, và nét guilloche (hoa văn sóng đan nhau chống làm giả) chỉ xuất hiện ở đúng một chỗ: nơi kết quả được kiểm chứng.

Đây là màn hình công cụ: điều hướng, nút, bảng đều là loại người dùng đã quen. Thế giới tờ tiền chỉ góp bốn thứ: kiểu chữ, bảng màu, độ dày thông tin và con dấu kiểm chứng.

**Key Characteristics:**
- Thanh điều hướng xanh dương nhạt trên nền polymer trắng ngả xanh; xanh dương tờ 20.000đ cho nút chính và con dấu.
- Mỗi màu mệnh giá có một nghĩa duy nhất: chú ý, đã khớp, bước đang xử lý.
- Chữ số dạng bảng (tabular) ở mọi nơi.
- Con dấu guilloche là dấu hiệu riêng, vẽ bằng hình học thật, không phải ảnh.

## Colors

Bảng màu tiết chế theo mệnh giá: một màu khung đậm, ba màu trạng thái, mọi sắc độ phụ suy ra từ chúng.

### Primary
- **Xanh dương tờ 20.000đ** (blue-20k): nút chính, nét hoa văn con dấu. Bản đậm hơn (blue-deep) cho hover; blue-ink cho chữ xanh trên nền sáng.
- **Xanh dương nhạt** (blue-tint): nền thanh điều hướng và dải bước tiếp theo; blue-tint-strong cho hover trên thanh.

### Secondary
- **Cam đỏ tờ 200.000đ** (attention-200k): chỉ cho chỗ cần người dùng chú ý: lệch tiền, lỗi, kiểm chứng hỏng.
- **Xanh lá tờ 100.000đ** (matched-100k): đã khớp, phép kiểm đạt, dịch vụ hoạt động.

### Tertiary
- **Tím hồng tờ 50.000đ** (active-50k): dành riêng cho bước đang xử lý trong quy trình.

### Neutral
- **Nền polymer** (polymer-ground): nền trang, trắng ngả xanh dương nhạt, không ngả kem.
- **Mực** (ink) và **mực nhạt** (ink-soft): chữ chính và chữ phụ.
- **Đường kẻ** (line, line-soft): viền panel và đường chia hàng.

### Named Rules
**Quy tắc mệnh giá.** Mỗi màu mệnh giá chỉ mang một nghĩa. Không dùng cam đỏ để trang trí, không dùng xanh lá cho thứ chưa được kiểm.
**Quy tắc không xám tùy tiện.** Không thêm màu xám mới; chữ phụ, đường kẻ và nền nhạt đều lấy từ mực và các sắc độ tint đã có.
**Quy tắc một màu cho bước đang chạy.** Tím hồng tờ 50.000đ chỉ xuất hiện ở bước đang xử lý, không ở đâu khác.

## Typography

**Body Font:** Be Vietnam Pro (dự phòng system-ui), tự host qua @fontsource, có đủ dấu tiếng Việt.

**Character:** Một kiểu chữ không chân do người Việt thiết kế, rõ ở cỡ nhỏ, dấu thanh không bị chồng; số dạng bảng để cột tiền thẳng hàng.

### Hierarchy
- **Display** (700, clamp 28–36px, 1.15): tiêu đề trang.
- **Headline** (600, 22px, 1.3): dải bước tiếp theo.
- **Title** (600, 18px, 1.3): tiêu đề panel.
- **Body** (400, 16px, 1.55): nội dung; độ dài dòng tối đa khoảng 65 ký tự cho đoạn mô tả.
- **Label** (500, 14px): nhãn trạng thái, chú thích.

### Named Rules
**Quy tắc chữ số thẳng cột.** Mọi con số dùng `font-variant-numeric: tabular-nums`.

## Layout

Thanh điều hướng cố định 260px bên trái, thu gọn được còn 76px (chỉ biểu tượng) bằng nút nhỏ ở góc trên bên phải cạnh tên, trạng thái được nhớ trong trình duyệt; nội dung tối đa 1280px, lề 40px (co giãn theo màn hình). Tổng quan chia hai cột: nội dung chính và cột 340px cho con dấu kiểm chứng; dưới 860px gộp thành một cột. Dưới 760px thanh điều hướng thành thanh tab cố định ở đáy, lề trang 16px. Khoảng cách: 8px trong nhóm, 16px giữa các phần tử, 28px giữa các khối.

## Elevation & Depth

Phẳng theo tầng màu: panel trắng nằm trên nền polymer, ngăn bằng đường kẻ 1px. Chỉ thanh tab đáy trên điện thoại có bóng nhẹ hướng lên để tách khỏi nội dung cuộn.

### Shadow Vocabulary
- **Thanh tab đáy** (`box-shadow: 0 -6px 18px rgb(31 95 174 / 0.2)`): chỉ trên điện thoại.

## Shapes

Góc bo vừa phải: 12px cho panel và dải bước tiếp theo, 8px cho nút và mục điều hướng, bo tròn hẳn cho chip trạng thái và số thứ tự bước.

## Components

### Buttons
- **Shape:** bo 8px, cao tối thiểu 44px.
- **Primary:** nền xanh dương tờ 20.000đ, chữ on-blue, đậm 600.
- **Hover / Focus:** nền đậm hơn; vòng focus mảnh 2px xanh dương mờ, chỉ hiện khi dùng bàn phím.

### Navigation
- **Máy tính:** thanh dọc xanh dương nhạt, viền phải rail-line; mục thường chữ rail-ink, mục đang mở là ô trắng chữ blue-ink có bóng rất nhẹ. Nút thu gọn là ô 36px chỉ có biểu tượng, không viền, ở góc trên bên phải cạnh tên. Khi thu gọn, logo và chữ mờ đi (180ms), nút trượt về đúng chỗ logo; tâm mọi biểu tượng thẳng cột ở 38px. Tên studio có độ rộng cố định để không xếp lại chữ khi thanh co giãn. Mục đang mở là ô trắng, không bóng, không viền.
- **Điện thoại:** thanh tab cố định ở đáy, biểu tượng trên nhãn.

### Cards / Containers
- **Panel:** nền trắng, viền line-soft 1px, bo 12px, đệm 24px. Không lồng panel trong panel.

### Con dấu kiểm chứng (signature)
Bốn vòng hoa văn guilloche, mỗi vòng là một phép kiểm độc lập. Chưa kiểm: nét xanh nhạt. Đạt: nét xanh đậm, vẽ dần một lần khi xuất hiện. Hỏng: vòng đứt một đoạn và chuyển cam đỏ; lõi đổi màu theo kết quả.

### Nút phụ, nút nguy hiểm, nút biểu tượng
- **Nút phụ (quiet):** nền trắng, viền line, chữ blue-ink; hover nền blue-tint.
- **Nút nguy hiểm:** nền attention-200k chữ trắng, chỉ dùng trong hộp thoại xác nhận xóa.
- **Nút biểu tượng:** ô 36px không viền, hover nền blue-tint; dùng cho xóa, phân trang.

### Nhãn trạng thái (badge)
Viên tròn 13px đậm: Đã đọc (matched), Đang đọc (active, màu bước đang chạy), Lỗi (attention), Không có bảng (blue-tint).

### Vùng tải tệp và danh sách bộ dữ liệu
- Vùng tải: panel trắng viền đứt 1.5px; khi kéo tệp vào, viền và nền chuyển xanh. Mỗi tệp đang tải có dòng tiến độ riêng.
- Danh sách: mỗi bộ một hàng, thanh 4px dài theo số dòng (so với bộ lớn nhất), nhãn trạng thái và số dòng bên phải, nút xóa mở hộp thoại xác nhận.

### Bảng xem trước
Đầu bảng nền blue-tint dính trên cùng khi cuộn; cột "Dòng gốc" dính bên trái, căn phải, chữ ink-soft. Ô trống để trống, không tô màu (việc đánh giá ô trống thuộc bước làm sạch). Phân trang 50 dòng.

### Hồ sơ cột
Lưới thẻ (tối thiểu 280px), mỗi cột một thẻ: tên, nhãn dạng dữ liệu (Mã, Số, Ngày, Điện thoại, Chữ, Trống), nhãn "Có số 0 ở đầu" màu active khi có; ba số Có giá trị / Trống / Khác nhau, thanh 4px tỷ lệ có giá trị; giá trị mẫu dạng mã nhỏ.

### Hộp thoại xác nhận
Thẻ `<dialog>` gốc, bo 12px, nền mờ ink 35%; nút Hủy (phụ) và nút hành động (nguy hiểm).

## Do's and Don'ts

### Do:
- **Do** giữ mỗi màu mệnh giá đúng một nghĩa (Quy tắc mệnh giá).
- **Do** dùng con dấu guilloche chỉ cho kết quả kiểm chứng.
- **Do** dùng biểu tượng lucide nét 1.8, không dùng emoji hay ký tự thay biểu tượng.

### Don't:
- **Don't** biến giao diện thành bản sao ChatGPT chỉ có ô chat trống.
- **Don't** dồn bảng biểu dày đặc kiểu phần mềm kế toán cũ.
- **Don't** thêm gradient, ánh sáng hay hiệu ứng chuyển động trang trí.
- **Don't** rải hoa văn guilloche làm nền hay trang trí.
