"""
경쟁사 홈페이지 분석 보고서 자동 생성 웹앱
Flask + Claude API + ReportLab
"""
import os
import uuid
import threading
import json
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template
from dotenv import load_dotenv

load_dotenv(override=True)
print(f"[STARTUP] ANTHROPIC_API_KEY set: {bool(os.getenv('ANTHROPIC_API_KEY'))}")

from modules.crawler import crawl_website
from modules.analyzer import analyze_with_claude
from modules.pdf_generator import generate_pdf
from modules.history_manager import HistoryManager

# ── 앱 설정 ────────────────────────────────────────────────
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["REPORTS_FOLDER"] = "reports"
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024  # 80MB

for folder in ["uploads", "reports", "history", "fonts"]:
    os.makedirs(folder, exist_ok=True)

history_mgr = HistoryManager("history")

# 인메모리 작업 상태 저장소
jobs: dict = {}
jobs_lock = threading.Lock()

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _update_job(job_id: str, **kwargs):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)


# ── 라우트 ─────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    url     = request.form.get("url", "").strip()
    own_url = request.form.get("own_url", "").strip()
    uploaded_files = request.files.getlist("attachments")

    if not url:
        return jsonify({"error": "URL을 입력해주세요."}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if own_url and not own_url.startswith(("http://", "https://")):
        own_url = "https://" + own_url

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "progress": 0,
            "message": "분석 대기 중...",
            "created_at": datetime.now().isoformat(),
        }

    # 첨부파일 저장
    saved_paths = []
    for f in uploaded_files:
        if not f or not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        safe_name = f"{job_id}_{f.filename}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
        f.save(save_path)
        saved_paths.append(save_path)

    # 백그라운드 분석 시작
    thread = threading.Thread(
        target=_run_analysis,
        args=(job_id, url, own_url, saved_paths),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


def _run_analysis(job_id: str, url: str, own_url: str, attachment_paths: list):
    """백그라운드 분석 파이프라인."""
    try:
        # 1. 크롤링 (경쟁사 + 자사 동시)
        if own_url:
            _update_job(job_id, status="crawling", progress=8,
                        message="경쟁사·자사 홈페이지 크롤링 중...")
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                fut_comp = ex.submit(crawl_website, url)
                fut_own  = ex.submit(crawl_website, own_url)
                crawl_data     = fut_comp.result()
                own_crawl_data = fut_own.result()
        else:
            _update_job(job_id, status="crawling", progress=10, message="홈페이지 크롤링 중...")
            crawl_data     = crawl_website(url)
            own_crawl_data = None

        # 2. Claude 분석
        _update_job(job_id, status="analyzing", progress=35, message="Claude AI 분석 중... (30~60초 소요)")
        analysis = analyze_with_claude(crawl_data, attachment_paths, own_crawl_data=own_crawl_data)

        # 3. PDF 생성
        _update_job(job_id, status="generating", progress=75, message="PDF 보고서 생성 중...")
        pdf_filename = f"report_{job_id}.pdf"
        pdf_path = os.path.join(app.config["REPORTS_FOLDER"], pdf_filename)
        generate_pdf(url, crawl_data, analysis, attachment_paths, pdf_path,
                     own_url=own_url, own_crawl_data=own_crawl_data)

        # 4. 히스토리 저장
        _update_job(job_id, status="saving", progress=92, message="결과 저장 중...")
        entry = history_mgr.save(url, "all", analysis, pdf_filename, own_url=own_url)

        own_company_name = ""
        if own_crawl_data:
            own_company_name = analysis.get("own_company", {}).get("overview", {}).get("company_name", "")

        _update_job(
            job_id,
            status="done",
            progress=100,
            message="분석 완료!",
            pdf_filename=pdf_filename,
            history_id=entry["id"],
            company_name=entry["summary"].get("company_name", ""),
            own_company_name=own_company_name,
        )

    except Exception as e:
        import traceback
        _update_job(
            job_id,
            status="error",
            progress=0,
            message=f"오류 발생: {str(e)}",
            error_detail=traceback.format_exc(),
        )

    finally:
        pass


@app.route("/status/<job_id>")
def status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify(job)


@app.route("/download/<filename>")
def download(filename: str):
    # 경로 순회 방지
    filename = Path(filename).name
    path = os.path.join(app.config["REPORTS_FOLDER"], filename)
    if not os.path.exists(path):
        return jsonify({"error": "파일을 찾을 수 없습니다."}), 404
    return send_file(path, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/history")
def history_list():
    entries = history_mgr.list_all()
    return jsonify(entries)


@app.route("/history/<history_id>")
def history_detail(history_id: str):
    entry = history_mgr.get(history_id)
    if not entry:
        return jsonify({"error": "기록을 찾을 수 없습니다."}), 404
    return jsonify(entry)


@app.route("/history/<history_id>", methods=["DELETE"])
def history_delete(history_id: str):
    deleted = history_mgr.delete(history_id)
    if not deleted:
        return jsonify({"error": "기록을 찾을 수 없습니다."}), 404

    # 연결된 PDF 파일도 삭제 시도
    entry_data = {}  # 이미 삭제됨
    return jsonify({"success": True})


@app.route("/compare/<id1>/<id2>")
def compare(id1: str, id2: str):
    e1 = history_mgr.get(id1)
    e2 = history_mgr.get(id2)
    if not e1 or not e2:
        return jsonify({"error": "비교할 기록을 찾을 수 없습니다."}), 404
    result = history_mgr.compare(e1, e2)
    return jsonify(result)


@app.route("/history/by-url")
def history_by_url():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify([])
    entries = history_mgr.find_by_url(url)
    return jsonify(entries)


@app.route("/health")
def health():
    api_key_set = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())
    font_ok = os.path.exists(os.path.join("fonts", "NanumGothic.ttf"))
    return jsonify({
        "status": "ok",
        "api_key_configured": api_key_set,
        "font_available": font_ok,
        "history_count": len(history_mgr.list_all()),
    })


if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("경쟁사 홈페이지 분석 보고서 생성기")
    print("=" * 50)
    print(f"API 키: {'설정됨' if os.getenv('ANTHROPIC_API_KEY') else '미설정 (.env 파일 확인)'}")
    print(f"NanumGothic 폰트: {'있음' if os.path.exists('fonts/NanumGothic.ttf') else '없음 (python setup_fonts.py 실행)'}")
    print(f"서버 주소: http://localhost:{PORT}")
    print("=" * 50)
    app.run(debug=False, port=PORT, host="0.0.0.0")
