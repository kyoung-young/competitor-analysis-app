"""
NanumGothic 폰트 다운로드 스크립트
최초 1회 실행: python setup_fonts.py
"""
import os
import requests

FONTS = {
    "NanumGothic.ttf": "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf",
    "NanumGothicBold.ttf": "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf",
    "NanumGothicExtraBold.ttf": "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-ExtraBold.ttf",
}

FALLBACK_FONTS = {
    "NanumGothic.ttf": "https://noto-website-2.storage.googleapis.com/pkgs/NotoSansCJKkr-hinted.zip",
}


def download_fonts():
    font_dir = os.path.join(os.path.dirname(__file__), "fonts")
    os.makedirs(font_dir, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for filename, url in FONTS.items():
        path = os.path.join(font_dir, filename)
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            print(f"[OK] {filename} 이미 존재")
            continue

        print(f"[다운로드] {filename} ...")
        try:
            r = requests.get(url, headers=headers, timeout=30, stream=True)
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            size = os.path.getsize(path)
            print(f"[완료] {filename} ({size:,} bytes)")
        except Exception as e:
            print(f"[실패] {filename}: {e}")

    # 결과 확인
    print("\n--- 폰트 상태 ---")
    for filename in FONTS:
        path = os.path.join(font_dir, filename)
        if os.path.exists(path):
            print(f"[OK] {filename}: {os.path.getsize(path):,} bytes")
        else:
            print(f"[없음] {filename}")


if __name__ == "__main__":
    download_fonts()
