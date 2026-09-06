# IAM Blast-Radius Experiment — Runnable Kit

ชุดสคริปต์สำหรับตอบ Research Question:
**"How does IAM permission scope affect the blast radius of a compromised cloud identity?"**

แนวคิด: สร้าง identity 3 ระดับ (Policy A/B/C) แล้วยิง **Fixed Action Set ชุดเดียวกัน 100 actions ครอบ 12 AWS services**
กับทุก identity → บันทึก SUCCESS/DENIED → คำนวณ **ASR** และ **Impact-Weighted Blast Radius**
→ ทำกราฟ/ตารางเปรียบเทียบ

ตัวแปรเดียวที่เปลี่ยนคือ IAM permission scope (independent variable) ทุกอย่างอื่นคงที่

**Live dashboard:** `docs/index.html` (เปิดในเบราว์เซอร์ หรือโฮสต์ฟรีด้วย GitHub Pages)

---

## โครงสร้างไฟล์

```
iam-blast-radius-lab/
├── policies/
│   ├── policy_a_narrow.json      # Least privilege: อ่าน S3 bucket เดียว + เขียน log ของตัวเอง
│   ├── policy_b_moderate.json    # Read กว้าง + operational write หลาย service (ไม่มี delete/IAM)
│   └── policy_c_broad.json       # PowerUser-like: s3:* ec2:* lambda:* ... + IAM read เท่านั้น
├── action_set.py                 # นิยาม 100 actions + service + category + weight (กำหนดก่อนทดลอง)
├── run_experiment.py             # ยิง action set กับทุก identity -> results_raw.json
├── compute_metrics.py            # คำนวณ ASR + Weighted Blast Radius + กราฟ
├── setup_lab.py                  # (ทางเลือก) สร้าง/ลบ IAM users + resource บน AWS sandbox
├── docs/index.html               # Dashboard (GitHub Pages)
└── results/                      # ผลลัพธ์ทั้งหมดออกที่นี่
```

---

## 2 โหมดการทำงาน

### โหมด MOCK — รันได้เลย ไม่ต้องมี AWS
ใช้ evaluator ในเครื่องอ่าน policy JSON แล้วตัดสิน Allow/Deny ของแต่ละ action
เหมาะกับการ **ทดสอบ pipeline การคำนวณ/กราฟให้เสร็จก่อน**

```bash
python3 run_experiment.py --mock
python3 compute_metrics.py
```

ผลตัวอย่าง (100 actions):

| Identity | Success | ASR % | Weighted BR % |
|----------|:------:|:-----:|:------:|
| Policy A |   6    |  6.0  |  3.9   |
| Policy B |  47    | 47.0  | 30.2   |
| Policy C |  88    | 88.0  | 77.6   |

> สังเกต: Policy C ทำได้ 88% แต่ WBR แค่ 77.6% เพราะ 12 อย่างที่ทำไม่ได้คือ IAM
> identity-mutation ที่น้ำหนักสูงสุด (ESCALATE ×4) — PowerUser ที่กว้างมากก็ยังยกระดับสิทธิ์ตัวเองไม่ได้

### โหมด SIMULATE — ใช้ IAM Policy Simulator จริงของ AWS (แนะนำสำหรับผลจริง)

`--simulate` จะส่ง policy JSON ทั้ง 3 ไปให้ **AWS IAM Policy Simulator** (`iam:SimulateCustomPolicy`)
ตัดสิน Allow/Deny ของทั้ง 100 actions ด้วย engine จริงของ AWS — แต่ **ไม่ต้องสร้าง S3/EC2/IAM
resource เลย และไม่แก้ไขอะไรจริง** จึงฟรีและปลอดภัย เหมาะกับ action set ขนาด 100 ที่การยิง API จริงทีละตัวไม่คุ้ม

```bash
python3 -m pip install boto3
# ตั้งค่า credential (sandbox) ที่มีสิทธิ์ iam:SimulateCustomPolicy
aws configure    # หรือใช้ env vars

python3 run_experiment.py --simulate --region us-east-1
python3 compute_metrics.py
```

> โหมดนี้สะท้อนการตัดสินใจจริงของ IAM (รวม explicit Deny และ wildcard) มากกว่า mock
> ที่ match action แบบง่าย ๆ อย่างเดียว

`setup_lab.py` มีไว้เผื่อคุณอยากสร้าง IAM users/resource จริงเพื่อทดสอบ + เก็บ CloudTrail
แต่สำหรับวัด blast radius ล้วน ๆ โหมด simulate ไม่จำเป็นต้องใช้

---

## Metric ที่ใช้

**Metric A — Action Success Rate**
```
ASR = (Successful Actions / Total Attempted Actions) × 100
```

**Metric B — Impact-Weighted Blast Radius** (ถ่วงน้ำหนักตามความรุนแรง)
```
weights: READ=1, WRITE=2, DESTROY=3, ESCALATE=4
WBR = Σ(weight ของ action ที่สำเร็จ) / Σ(weight ของ action ทั้งหมด) × 100
```

> **สำคัญ:** AWS ไม่มี metric สำเร็จรูปสำหรับ blast radius — AWS ให้แค่ผล Allow/Deny
> ส่วน ASR/WBR และตัวเลขน้ำหนักเป็นสิ่งที่งานนี้นิยามเอง (กำหนดใน `action_set.py`
> **ก่อน** เก็บผล) ต้องระบุใน limitations ว่าเป็น proposed scheme ไม่ใช่มาตรฐาน AWS

**100 actions แบ่งเป็น:** READ 41 · WRITE 26 · DESTROY 20 · ESCALATE 13 (น้ำหนักรวม 205)

---

## Output ที่ได้

- `results/results_raw.json` — ผลดิบทุกแถว (identity × action) → dashboard อ่านไฟล์นี้
- `results/metrics.csv` — สรุปต่อ identity (ASR, WBR, นับตาม category)
- `results/results_detail.csv` — matrix SUCCESS/DENIED ราย action
- `results/blast_radius.png` — กราฟเปรียบเทียบ

---

## Dashboard (GitHub Pages)

หน้า `docs/index.html` จะพยายามโหลด `results/results_raw.json` ก่อน ถ้าไม่เจอจึงใช้ข้อมูลที่ฝังไว้
วิธีเผยแพร่: push ขึ้น GitHub → Settings → Pages → เลือก branch `main` โฟลเดอร์ `/docs`
พอรัน simulate ได้ผลจริง แค่ก็อป `results/results_raw.json` ทับใน `docs/results/` แล้ว
dashboard จะเปลี่ยนเป็นข้อมูลจริง และ badge จะขึ้นเป็น "AWS run" อัตโนมัติ

---

## เชื่อมกับงานวิจัย

AI-Enhanced attack (UNC6426) พา attacker ไปถึงจุดที่ได้ cloud identity มา — MVP นี้ isolate
ตัวแปรถัดไปคือ **IAM permission scope** แล้ววัดว่า identity นั้นสร้างความเสียหายได้แค่ไหน (blast radius)
โดยวัดเฉพาะ reachable actions ใน controlled environment — **ไม่** เคลมถึงความเสียหายทางธุรกิจจริง
