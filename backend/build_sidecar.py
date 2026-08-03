import subprocess
import shutil
import os
import sys

def get_target_triple():
    try:
        output = subprocess.check_output(["rustc", "-vV"]).decode("utf-8")
        for line in output.splitlines():
            if line.startswith("host: "):
                return line.split("host: ")[1].strip()
    except Exception as e:
        print(f"Warning: could not get rustc target triple: {e}")
        if sys.platform == "darwin":
            if os.uname().machine == "arm64":
                return "aarch64-apple-darwin"
            return "x86_64-apple-darwin"
        elif sys.platform == "win32":
            return "x86_64-pc-windows-msvc"
        return "x86_64-unknown-linux-gnu"
    return "unknown"

def main():
    target = get_target_triple()
    bin_name = "studio-ops-backend"
    
    print("Building backend with PyInstaller...")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", 
        "--onefile", 
        "--name", bin_name,
        "--clean",
        "run.py"
    ], check=True)
    
    ext = ".exe" if sys.platform == "win32" else ""
    src_bin = os.path.join("dist", bin_name + ext)
    
    dest_dir = os.path.join("..", "src-tauri", "binaries")
    os.makedirs(dest_dir, exist_ok=True)
    
    dest_bin = os.path.join(dest_dir, f"{bin_name}-{target}{ext}")
    shutil.copy2(src_bin, dest_bin)
    print(f"Copied backend binary to {dest_bin}")

if __name__ == "__main__":
    main()
