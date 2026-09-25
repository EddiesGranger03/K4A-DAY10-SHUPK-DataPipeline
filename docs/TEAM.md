# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `SHUPK`
- **Mã Nhóm / Lớp:** `K4A-DAY10`
- **Tên Repository Nộp Bài:** `K4A-DAY10-SHUPK-DataPipeline`

---

## # Thành viên

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Nguyễn Khánh Sơn | 2A202602388 | 26ai.sonnk2@vinuni.edu.vn | **Trưởng nhóm / Pipeline Integrator** — `core/config.py`, `phase1.py`, `corruption_flow.py`, điều phối tích hợp toàn luồng, quản lý Git nhánh `main` | [Bên dưới](#nguyenkhanhson-2a202602388) |
| 2 | Lê Châu Trần Phát | 2A202602545 | 26ai.phatlct@vinuni.edu.vn | **Data Foundation & Recovery** — `crossref.py`, `cleaning.py`, thu thập & làm sạch dữ liệu, cơ chế Idempotent Repair | [Bên dưới](#lechautranphat-2a202602545) |
| 3 | Nguyễn Nam Khánh | 2A202602568 | 26ai.khanhnn@vinuni.edu.vn | **RAG & Vector Index** — `retrieval/index.py`, `embeddings.py`, ChromaDB 3 collections, QA Agent | [Bên dưới](#nguyennamkhanh-2a202602568) |
| 4 | Bùi Thị Thu Uyên | 2A202602613 | 26ai.uyenbtt@vinuni.edu.vn | **Observability & Evaluation** — `quality.py` (GX 1.x), `testset.py`, `reporting.py`, báo cáo 3 trạng thái | [Bên dưới](#buithithuuyen-2a202602613) |
| 5 | Ngô Xuân Hoàng | 2A202602597 | 26ai.hoangnx2@vinuni.edu.vn | **Corruption Suite & QA** — `corruption.py`, `testset.py`, đo lường suy giảm, kiểm thử end-to-end | [Bên dưới](#ngoxuanhoang-2a202602597) |

---

## # Cá nhân

### ## NguyenKhanhSon-2A202602388
- **Vai trò:** Trưởng nhóm & Điều phối Pipeline (Pipeline Integrator).
- **Công việc chi tiết đã hoàn thành:**
  - Thiết lập cấu hình hệ thống `core/config.py`: Settings dataclass, Paths dataclass, load_settings() với dotenv.
  - Kết nối toàn bộ luồng thực thi trong `src/pipelines/phase1.py` (10 bước baseline end-to-end).
  - Kết nối luồng `src/pipelines/corruption_flow.py` (8 bước: corrupt → evaluate → repair → compare).
  - Quản lý Git nhánh `main`, review pull request của từng thành viên, đảm bảo tính nhất quán của artifacts.
  - Viết `script/run_phase1.py` và `script/run_corruption_flow.py` làm entrypoint chuẩn.
- **Điều học được / Đóng góp chính:**
  - Nắm vững thiết kế Idempotent Pipeline: pipeline có thể chạy lại nhiều lần mà không sinh ra artifact sai lệch.
  - Hiểu sâu về quản lý trạng thái luồng dữ liệu đa tầng (Raw → Clean → Corrupted → Repaired).
  - Kinh nghiệm tích hợp nhiều module Python độc lập thành một hệ thống chạy liên tục.

### ## LeChauTranPhat-2A202602545
- **Vai trò:** Phụ trách Ingestion, Làm sạch & Phục hồi dữ liệu.
- **Công việc chi tiết đã hoàn thành:**
  - Xây dựng module thu thập Crossref API với cơ chế Fallback offline tự động (`src/ingestion/crossref.py`): `parse_crossref_payload()`, `fetch_source_records()`, `load_raw_records()`.
  - Lưu trữ 2 file Raw Artifact: `data/raw/crossref_response.json` (nguyên bản API) và `data/raw/crossref_records.json` (parsed PaperRecord list) để đảm bảo Data Lineage.
  - Chuẩn hóa schema, loại bỏ JATS XML tags, tính toán `age_days`, sinh `text_for_embedding` 5-part trong `src/ingestion/cleaning.py`.
  - Thực thi cơ chế Idempotent Repair: đọc lại từ raw snapshot để ghi đè dữ liệu hỏng.
- **Điều học được / Đóng góp chính:**
  - Kỹ thuật Data Lineage: tại sao phải giữ nguyên bản thô (raw preservation) trước mọi biến đổi.
  - Kỹ năng xử lý text nâng cao: chuẩn hóa whitespace, parse JATS XML, compact_join.

### ## NguyenNamKhanh-2A202602568
- **Vai trò:** Phụ trách RAG, Vector Database & Embedding.
- **Công việc chi tiết đã hoàn thành:**
  - Quản lý mô hình embedding `sentence-transformers/all-MiniLM-L6-v2` trong `src/retrieval/embeddings.py`.
  - Nạp và quản lý 3 ChromaDB collection riêng biệt (`papers-baseline`, `papers-corrupted`, `papers-repaired`) trong `src/retrieval/index.py`.
  - Xây dựng QA Agent: `answer_question()` trong `src/retrieval/qa.py` truy vấn ngữ cảnh chuẩn xác từ vector store.
  - Triển khai `src/retrieval/llm.py` hỗ trợ multi-provider (mock, gemini, openai, anthropic, openrouter, ollama).
- **Điều học được / Đóng góp chính:**
  - Cách cô lập 3 không gian vector riêng biệt để đảm bảo so sánh khách quan giữa dữ liệu sạch và dữ liệu bị lỗi.
  - Kỹ thuật Retrieval-Augmented Generation (RAG) end-to-end từ embedding đến answer generation.

### ## BuiThiThuUyen-2A202602613
- **Vai trò:** Phụ trách Data Observability & Benchmark Evaluation.
- **Công việc chi tiết đã hoàn thành:**
  - Thiết lập Quality Gate theo chuẩn **Great Expectations 1.x** với ephemeral context (`gx.get_context(mode="ephemeral")`) trong `src/observability/quality.py`.
  - Định nghĩa 4 Expectations bắt buộc: `ExpectTableRowCountToBeBetween`, `ExpectColumnValuesToNotBeNull`, `ExpectColumnValuesToBeUnique`, `ExpectColumnValueLengthsToBeBetween`.
  - Giám sát Freshness SLA: cảnh báo `is_fresh = False` khi > 25% bài báo có `age_days > 180`.
  - Xây dựng bộ 10+ câu hỏi benchmark 4 loại trong `src/evaluation/testset.py`.
  - Thiết kế và sinh báo cáo Markdown cho Phase 1 và đối chiếu 3 trạng thái (`src/observability/reporting.py`).
- **Điều học được / Đóng góp chính:**
  - Cách thiết lập hệ thống cảnh báo sớm (Data Observability Gate) chặn đứng Silent Failure.
  - Cú pháp GX 1.x chuẩn mới khác hoàn toàn so với GX 0.x (không dùng `context.sources.pandas_default`).

### ## NgoXuanHoang-2A202602597
- **Vai trò:** Phụ trách Corruption Suite, Đo lường suy giảm & Kiểm thử End-to-End.
- **Công việc chi tiết đã hoàn thành:**
  - Triển khai 6 kịch bản làm bẩn dữ liệu trong `src/ingestion/corruption.py`:
    1. Drop 20% bản ghi mới nhất (simulate data loss).
    2. Blank summary (simulate scraping failure).
    3. Inject noise characters (simulate encoding corruption).
    4. Truncate title < 8 ký tự (simulate truncation bug).
    5. Age published date 365 ngày (simulate stale data).
    6. Duplicate rows (simulate re-run without dedup).
  - Ghi log chi tiết 6 loại lỗi vào `data/results/corruption_log.json`.
  - Kiểm thử pipeline end-to-end: chạy `run_phase1.py` → `run_corruption_flow.py`, đối chiếu kết quả 3 trạng thái.
  - Đảm bảo toàn bộ pipeline tái lặp được (Idempotent) và chạy sạch từ đầu.
- **Điều học được / Đóng góp chính:**
  - Hiện tượng Silent Failure: dữ liệu bẩn không báo lỗi nhưng làm giảm chất lượng AI một cách âm thầm.
  - Tầm quan trọng của việc đo lường định lượng (Hit Rate, Token F1) để phát hiện suy giảm.
