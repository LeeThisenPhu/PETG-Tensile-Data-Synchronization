"""Run the complete PETG synchronization pipeline with one command."""
from pathlib import Path
import argparse, os, subprocess, sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"


def run(script, *args, env=None):
    command = [sys.executable, str(SRC / script), *map(str, args)]
    print("\n$", " ".join(command), flush=True)
    subprocess.run(command, check=True, env=env)


def main():
    parser = argparse.ArgumentParser(description="Đồng bộ dữ liệu kéo PETG Maxtest–Terminal")
    parser.add_argument("--data-zip", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    parser.add_argument("--skip-plots", action="store_true", help="Không tạo hình khi chỉ cần CSV")
    args = parser.parse_args()
    output = args.output.resolve()

    run("prepare_inputs.py", "--data-zip", args.data_zip.resolve(), "--matrix", args.matrix.resolve(), "--output", output)
    env = os.environ.copy()
    env["PETG420_OUTPUT"] = str(output)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    run("processing.py", env=env)
    if not args.skip_plots:
        run("plots.py", env=env)
    run("export_excel.py", "--output", output, env=env)
    print(f"\nHoàn tất. Kết quả: {output}")


if __name__ == "__main__":
    main()
