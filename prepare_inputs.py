"""Prepare the raw ZIP and experimental matrix for the processing pipeline."""
from pathlib import Path
import argparse, hashlib, json, sys, zipfile
import openpyxl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def safe_extract(zip_path: Path, destination: Path) -> list[dict]:
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    root = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            target = (destination / info.filename).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"Đường dẫn không an toàn trong ZIP: {info.filename}")
            if info.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            content = archive.read(info)
            target.write_bytes(content)
            manifest.append({
                "path": target.relative_to(destination.parent).as_posix(),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
    return manifest


def workbook_to_json(excel_path: Path) -> dict:
    workbook = openpyxl.load_workbook(excel_path, data_only=False)
    result = {}
    for sheet in workbook:
        result[sheet.title] = [
            [value.isoformat() if hasattr(value, "isoformat") else value for value in row]
            for row in sheet.values
        ]
    return result


def main():
    parser = argparse.ArgumentParser(description="Chuẩn bị dữ liệu đầu vào PETG")
    parser.add_argument("--data-zip", type=Path, required=True, help="Data_mau_thu.zip")
    parser.add_argument("--matrix", type=Path, required=True, help="Excel ma trận thực nghiệm")
    parser.add_argument("--output", type=Path, required=True, help="Thư mục kết quả")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = safe_extract(args.data_zip, args.output / "source")
    (args.output / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    matrix = workbook_to_json(args.matrix)
    (args.output / "input_workbook.json").write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Đã chuẩn bị {len(manifest)} file nguồn tại {args.output}")


if __name__ == "__main__":
    main()
