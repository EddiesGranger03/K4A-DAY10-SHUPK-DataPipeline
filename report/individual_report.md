# Member Role Report - Day 10: Data Pipeline & Data Observability

> Bao cao nay duoc dien theo code va artifact dang co trong repository. Bo sung ho ten, MSSV va ten nhom truoc khi nop.

## 1. Thong tin ca nhan

| Thong tin | Noi dung |
| --- | --- |
| Ho va ten | Bùi Thị Thu Uyên |
| MSSV | 2A202602613 |
| Khoa/Lop | K4-L3A |
| Ten nhom | SHUPK |
| Vai tro chinh | Pipeline integration, quality gate va evaluation review |
| Repository | K4-L3A-Day10-Data-Pipeline-Data-Observability |
| Ngay hoan thanh | 2026-09-25 |

## 2. Vai tro va pham vi cong viec

| Module/deliverable | File/h function phu trach | Input | Output ban giao | Trang thai |
| --- | --- | --- | --- | --- |
| Quality gate va freshness | `src/observability/quality.py`, `src/pipelines/phase1.py` | Clean dataframe, GX expectations | Quality report, freshness report, gate truoc indexing | Da trien khai; da bo sung enforce gate |
| Corruption va repair flow | `src/pipelines/corruption_flow.py`, `src/ingestion/corruption.py` | Baseline clean data, raw snapshot | Corruption log, repaired dataset, comparison report | Da trien khai; repaired gate da duoc kiem soat |
| Evaluation contract | `src/evaluation/testset.py`, `src/evaluation/metrics.py` | Clean dataframe, test questions, answers | Test set 10 cau, Hit Rate, Token F1, judge metrics | Da trien khai; da sua F1 va validate contract |
| Vector manifest portability | `src/retrieval/index.py` | Chroma path, embedding manifest | Manifest dung relative path, load tuong thich path cu | Da trien khai |

## 3. Ket qua theo vai tro

| Nhiem vu da thuc hien | File/h function/artifact | Ket qua ban giao | Cach xac minh |
| --- | --- | --- | --- |
| Chan du lieu khong dat quality hoac freshness truoc indexing | `phase1.main`, `quality.run_data_quality_checks` | Baseline chi duoc index khi `gate_passed=True` | `python -m compileall -q src script` |
| Bao cao dung trang thai gate ket hop | `observability.reporting._gate` | Report dung `gate_passed`, khong nham `success` cua GX | Compile va doc logic report |
| Kiem soat repaired data | `corruption_flow.main` | Repair fail thi dung truoc index/evaluate | Compile va doc control flow |
| Sua Token F1 | `evaluation.metrics._token_f1` | Dung Counter, giu tan suat token lap | Unit smoke check trong moi truong Python |
| Bat buoc test set dung hop dong | `evaluation.testset.build_test_set` | 10 cau, du 4 loai theo phan bo 3/3/2/2 | Dataframe synthetic smoke check |
| Lam manifest Chroma portable | `retrieval.index.build/load` | Luu relative path, load ca path relative va absolute | Compile va doc load path |

## 4. Giai thich phan ky thuat da thuc hien

### Van de can giai quyet

Pipeline co nguy co silent failure: du lieu stale co the van duoc dua vao Chroma, report co the hien quality pass du freshness fail, va test/evaluation co the cho ket qua khong dung hop dong. Ngoai ra manifest Chroma ghi absolute path lam ket qua khong chay lai duoc tren checkout khac.

### Cach trien khai

- `quality.py` tinh `gate_passed` tu ket qua GX va freshness SLA.
- `phase1.py` dung pipeline truoc buoc index neu `gate_passed` la false.
- `corruption_flow.py` van index corrupted data de do tac dong, nhung repaired data phai pass gate truoc khi index.
- Token F1 dung `Counter` de tinh overlap theo tan suat thay vi bien token thanh set.
- Test set kiem tra ca so luong cau va phan bo question type truoc khi ghi file.
- Chroma manifest luu duong dan tuong doi voi project root; loader van ho tro manifest cu dung absolute path.

### Input, output va contract

| Thanh phan | Mo ta |
| --- | --- |
| Input | Raw Crossref snapshot, clean dataframe, settings va test set |
| Output | Quality/freshness reports, metrics, answers, embeddings manifest va comparison report |
| Module phu thuoc | `core.config`, `ingestion.cleaning`, `observability.quality`, `retrieval.index` |
| Module su dung output | `phase1.py`, `corruption_flow.py`, cac bao cao Markdown |
| Dieu kien loi | GX fail, freshness fail, test set thieu cau/loai, repaired data khong pass gate |

### Cach xac minh

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m compileall -q src script
.\.venv\Scripts\python.exe script\run_phase1.py
.\.venv\Scripts\python.exe script\run_corruption_flow.py
```

- Ket qua mong doi: compile pass; baseline chi index data pass gate; corruption flow tao du ba bo metrics va comparison report.
- Ket qua da xac minh: compile toan bo source pass. End-to-end chua hoan tat do Torch tren Windows gap `WinError 1114` khi nap `c10.dll`.
- Artifact: cac file runtime trong `data/clean`, `data/eval`, `data/results`, `data/quality` va `data/reports` se duoc tao sau khi xu ly blocker moi truong.

## 5. Mot quyet dinh ky thuat quan trong

- **Boi canh:** Freshness duoc tinh trong quality report nhung truoc do chua chan indexing.
- **Phuong an 1:** Chi log warning de pipeline tiep tuc.
- **Phuong an 2:** Gop GX va freshness thanh mot gate va dung truoc serving/indexing.
- **Phuong an da chon:** Phuong an 2.
- **Ly do:** Du lieu vuot SLA co the tao silent failure du quality schema van hop le; tiep tuc index se trai voi muc tieu observability.
- **Bang chung:** `quality.py` da co truong `gate_passed`; `phase1.py` va `corruption_flow.py` su dung truong nay lam dieu kien dung.

## 6. Mot loi hoac blocker da xu ly

- **Trieu chung:** Report co the hien PASSED khi GX pass nhung freshness fail; repaired data co the duoc index ma khong kiem tra gate.
- **Cach tai hien:** Doc control flow trong `phase1.py`, `corruption_flow.py` va ham `_gate` trong `reporting.py`.
- **Nguyen nhan goc:** Su dung `quality["success"]` thay vi `quality["gate_passed"]`.
- **Cach xu ly:** Dung `gate_passed` cho report va dieu kien truoc indexing; them repaired gate check.
- **Cach xac minh sau khi sua:** `compileall` pass; xem lai cac nhanh control flow lien quan.
- **Dieu hoc duoc:** Quality validation va freshness monitoring phai co mot contract gate duy nhat neu gate co nhiem vu bao ve serving layer.

### Blocker con lai

Import `sentence-transformers` nap Torch va loi native `WinError 1114` tai `torch\lib\c10.dll` trong moi truong hien tai. Can sua virtual environment/Torch CPU installation truoc khi chay embedding va end-to-end pipeline.

## 7. Hieu biet ve luong end-to-end

1. Crossref hoac snapshot offline duoc parse, lam sach va chuan hoa thanh dataframe; sau do dataframe duoc kiem tra quality/freshness truoc khi tao embedding va index vao Chroma.
2. Moi cau hoi trong test set co ground-truth document ID. Retrieval hit duoc tinh khi ID tai lieu dung nam trong ket qua truy van; answer quality duoc do bang Token F1 va judge metrics.
3. Quality checks kiem tra schema/noise/completeness/uniqueness; freshness monitoring do tuoi publication va ty le bai vuot nguong 180 ngay.
4. Cung mot test set giup so sanh baseline, corrupted va repaired tren cung cau hoi, tranh thay doi benchmark giua cac lan chay.
5. Repair thanh cong khi du lieu duoc tao lai tu raw snapshot, hai lan repair co content hash giong nhau, khop clean baseline va repaired quality/freshness gate pass.

## 8. Phan tich ket qua

| Metric/signal | Baseline | Corrupted | Repaired | Nhan xet |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | Chua chay | Chua chay | Chua chay | Can artifact metrics sau khi sua Torch |
| `mean_token_f1` | Chua chay | Chua chay | Chua chay | Da sua cach tinh Counter-based F1 |
| `judge_accuracy` | Chua chay | Chua chay | Chua chay | Khong dien so lieu khi chua co ket qua thuc |
| `mean_judge_score` | Chua chay | Chua chay | Chua chay | Khong dien so lieu khi chua co ket qua thuc |
| Quality checks | Co code | Co code | Co code | Artifact runtime chua duoc tao trong workspace hien tai |
| Freshness status | Chua chay | Chua chay | Chua chay | Se duoc ghi trong quality reports |

### Ket luan tu so lieu

Chua ket luan dinh luong truoc khi co ba file metrics va quality reports. Gia thuyet can kiem chung sau khi moi truong hoat dong la corruption se lam giam quality/freshness va repaired data se phuc hoi ve baseline do repair doc lai raw snapshot thay vi sua truc tiep dataframe loi.

## 9. Dieu hoc duoc va huong cai thien

1. Data quality chi co gia tri van hanh khi gate that su chan indexing.
2. Freshness la mot truc quan sat doc lap voi schema validation nhung can duoc ket hop khi ra quyet dinh serving.
3. Evaluation phai giu nguyen benchmark va phan biet ro so lieu da chay voi so lieu chua duoc xac minh.

Neu co them thoi gian, can sua Torch environment, chay ca hai entrypoint, luu artifact runtime va viet pytest regression cho quality gate, testset contract, token F1 va manifest portability.

## 10. Cam ket cua thanh vien

- [x] Noi dung bao cao phan biet phan da kiem chung va phan chua chay.
- [x] Khong ghi so lieu metrics khi chua co artifact thuc te.
- [x] Bao cao khong chua API key, token hoac secret.
- [ ] Bo sung ho ten, MSSV, ten nhom.
- [ ] Chay baseline va corruption flow sau khi sua blocker Torch.

**Ho va ten:** Can bo sung
**Ngay xac nhan:** 2026-09-25
