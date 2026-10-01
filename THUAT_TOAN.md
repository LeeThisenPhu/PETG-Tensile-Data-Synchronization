# Thuật toán đồng bộ

## 1. Đọc dữ liệu

`read_mt()` đọc bảng Maxtest và kiểm tra trục thời gian tăng liên tục. `read_terminal()` chấp nhận log có ngày giờ, chỉ có giờ hoặc chỉ có lực. Dòng Terminal không hoàn chỉnh được lưu riêng thay vì tự suy đoán.

## 2. Tái dựng trục thời gian Terminal

Khi log có timestamp, chương trình giữ nguyên thứ tự nhận dữ liệu, xử lý thời điểm trùng, thời điểm đi lùi ngắn và trường hợp qua nửa đêm. Khi log không có timestamp, chương trình dùng khoảng cách giữa số dòng nguồn làm trục tương đối.

## 3. Nhận dạng mốc

Tín hiệu lực chỉ được lọc trung vị để nhận dạng mốc. Lực xuất ra và UTS luôn dùng dữ liệu thô.

- `onset()`: tìm ba điểm liên tiếp vượt ngưỡng nền và nhiễu.
- `drop_anchor()`: tìm bước giảm lực lớn nhất sau vùng đạt ít nhất 90% lực đỉnh.

## 4. Ánh xạ thời gian

Khi có đủ hai mốc, hệ số ánh xạ được tính từ khoảng onset–gãy của hai thiết bị. Nếu mốc gãy yếu, chương trình có thể giữ nhịp timestamp hoặc ước lượng từ các mức lực 10–60%, sau đó kiểm tra trên các mức lực không dùng để fit.

## 5. Chuyển vị

Chương trình ưu tiên Elong. Khi Elong trùng Disp toàn bộ, chương trình dùng Disp và ghi `DISP_FALLBACK`. Giá trị tại onset được dùng làm zero. `interp_safe()` nội suy chuyển vị tại thời điểm lực Terminal và không nối qua khoảng mất dữ liệu dài.

## 6. Điểm cuối đường cong

Sau đỉnh lực, chương trình tìm điểm đầu tiên mà lực lọc giảm tới 50 kgf. Phần dữ liệu sau điểm này không được dùng để vẽ ứng suất–biến dạng. Ngưỡng 20 kgf được giữ như kiểm tra phụ cho gãy hoàn toàn.

## 7. Đại lượng cơ học

```text
F_N       = F_kgf × 9.80665
sigma_MPa = F_N / 40
epsilon_% = delta_L_mm / 50 × 100
UTS_MPa   = max(F_kgf thô) × 9.80665 / 40
```

## 8. Kiểm soát chất lượng

Các cờ chính:

- `SYNC_FAILED`: không thiết lập được đồng bộ.
- `SYNC_REVIEW`: sai lệch hình dạng lực vượt ngưỡng kiểm tra.
- `DISP_FALLBACK`: dùng chuyển vị đầu kéo.
- `ELONG_JUMP`: Elong nhảy trước điểm cắt.
- `FORCE_SPIKE_UNCONFIRMED`: đỉnh lực thô cần xác minh.
- `PARTIAL_MAXTEST`: Maxtest thiếu đoạn đầu.
- `NO_BELOW50`: log chưa ghi lực giảm đến 50 kgf.

Chương trình giữ dữ liệu thô, số dòng Terminal và lý do gắn cờ để người dùng truy vết.
