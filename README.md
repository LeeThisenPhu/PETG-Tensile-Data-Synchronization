# Đồng bộ dữ liệu kéo PETG từ Maxtest và Terminal

Dự án xử lý dữ liệu thí nghiệm kéo PETG in 3D khi hai hệ thống ghi dữ liệu độc lập:

- **Maxtest** cung cấp thời gian, `Elong`, `Disp` và hình dạng tín hiệu lực để căn thời gian.
- **Terminal** cung cấp lực thực nghiệm theo kgf.

Chương trình đồng bộ hai nguồn, lấy lực Terminal kết hợp với chuyển vị Maxtest, sau đó tính đường ứng suất–biến dạng kỹ thuật cho 84 trường hợp, mỗi trường hợp 5 mẫu.

## Nguyên lý

Hai mốc chính dùng để đồng bộ:

1. Thời điểm lực bắt đầu tăng ổn định.
2. Vùng sụt lực sau đỉnh.

Trục thời gian Terminal được ánh xạ sang Maxtest bằng:

```text
t_maxtest = offset + scale × t_terminal
```

Sau đồng bộ:

```text
F_N       = F_terminal_kgf × 9.80665
sigma_MPa = F_N / 40
epsilon_% = displacement_mm / 50 × 100
```

Thông số thí nghiệm:

- Chiều dài đo: `L0 = 50 mm`
- Tiết diện danh nghĩa: `10 × 4 = 40 mm²`
- Tốc độ kéo thực tế: `2 mm/min`
- Chuyển vị ưu tiên: `Elong`
- Chuyển vị thay thế: `Disp` khi Elong trùng Disp hoặc không sử dụng được
- Điểm kết thúc đồ thị: lực Terminal sau UTS giảm tới `50 kgf`
- Ngưỡng kiểm tra gãy hoàn toàn: `20 kgf`

UTS luôn lấy từ lực Terminal lớn nhất trong bản ghi thô. Chương trình không tự xóa đỉnh lực nghi vấn.

## Cấu trúc dự án

```text
PETG-Tensile-Synchronization/
├── run_pipeline.py          # Chạy toàn bộ quy trình
├── src/
│   ├── prepare_inputs.py    # Giải nén và đọc ma trận thực nghiệm
│   ├── processing.py        # Thuật toán đồng bộ và tính cơ tính
│   ├── plots.py             # Tạo biểu đồ từng mẫu và từng nhóm
│   ├── export_excel.py      # Tạo Excel tổng hợp
│   └── audit.py             # Kiểm tra dữ liệu thô
├── tests/
│   └── test_processing.py   # Kiểm thử thuật toán
├── docs/
│   └── THUAT_TOAN.md        # Giải thích thuật toán
├── requirements.txt
├── LICENSE
└── .gitignore
```

## Yêu cầu dữ liệu đầu vào

ZIP dữ liệu phải chứa cấu trúc:

```text
Data_mau_thu/
├── G001/
│   ├── 1/  # một file Maxtest .txt và một file Terminal .log
│   ├── 2/
│   ├── 3/
│   ├── 4/
│   └── 5/
├── G002/
└── ...
    └── G084/
```

File Excel ma trận phải có sheet `Ma trận thực nghiệm` và các dòng G001–G084.

Dữ liệu thô không được đưa vào repository mặc định vì dung lượng lớn và có thể chứa thông tin nghiên cứu chưa công bố.

## Cài đặt

```bash
git clone https://github.com/USERNAME/PETG-Tensile-Synchronization.git
cd PETG-Tensile-Synchronization
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux hoặc macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Chạy toàn bộ 420 mẫu

```powershell
python run_pipeline.py `
  --data-zip "D:\Du_lieu\Data_mau_thu.zip" `
  --matrix "D:\Du_lieu\MatranThucNghiem_ISO527_1B_PetG.xlsx" `
  --output "D:\Ket_qua_PETG"
```

Nếu chỉ cần CSV và Excel, không tạo biểu đồ:

```powershell
python run_pipeline.py `
  --data-zip "D:\Du_lieu\Data_mau_thu.zip" `
  --matrix "D:\Du_lieu\MatranThucNghiem_ISO527_1B_PetG.xlsx" `
  --output "D:\Ket_qua_PETG" `
  --skip-plots
```

## Kết quả

Mỗi mẫu tạo:

```text
G001/1/
├── Dong_bo_day_du.csv
├── Luc_Chuyen_vi.csv
├── Ket_qua.json
├── Dong_terminal_loi.json
├── Ung_suat_Bien_dang.png
├── Ung_suat_Bien_dang.svg
└── Kiem_tra_dong_bo.png
```

Kết quả tổng hợp:

- `Tong_hop_420_mau.csv`
- `Tong_hop_84_truong_hop.csv`
- `Tong_hop_420_mau.xlsx`
- `analysis.json`
- `groups.json`
- `So_sanh_5_mau.png` trong từng nhóm

## Kiểm thử

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

Bộ kiểm thử bao gồm đọc log, tái dựng timestamp, nội suy an toàn, bảo toàn lực thô, công thức đơn vị và phát hiện đỉnh lực nghi vấn.

## Giới hạn

- Hai thiết bị không dùng chung đồng hồ nên thời gian Terminal là thời gian được tái dựng.
- `Disp` là chuyển vị đầu kéo và có thể bao gồm độ mềm của máy, ngàm và mẫu. Kết quả có cờ `DISP_FALLBACK` cần được diễn giải phù hợp.
- Ứng suất dùng tiết diện danh nghĩa 40 mm², không hiệu chỉnh theo phần diện tích vật liệu thực tế của infill.
- Các cờ QA hỗ trợ kiểm tra dữ liệu, không thay thế hiệu chuẩn thiết bị hoặc đánh giá của người thực hiện thí nghiệm.

## Tác giả

Lê Thiên Phú - Chuyên ngành Cơ kỹ thuật - HCMUT. Linked in: www.linkedin.com/in/lethienphu2004




## Giấy phép

Mã nguồn phát hành theo giấy phép MIT. Dữ liệu thí nghiệm không nằm trong phạm vi giấy phép nếu không được công bố riêng.
