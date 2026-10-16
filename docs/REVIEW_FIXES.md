# การแก้ไขจากรีวิวโครงการ — 2026-10-16

ขอบเขตคือแก้ข้อบกพร่องของโปรแกรมและเตรียมหลักฐานตรวจสอบให้ทำซ้ำได้ ข้อมูลทดสอบทั้งหมดเป็นข้อมูลสมมติ ไม่มีการเพิ่มเกณฑ์ทางคลินิกหรือประกาศรับรองจากผล software tests

| ประเด็นรีวิว | การแก้ไข | หลักฐาน/ขอบเขตที่ยังต้องตรวจ |
|---|---|---|
| หน่วยหลุดจาก CSV และ alias | ตรวจหน่วยตั้งแต่ parser จนถึง domain validator; จับคู่ alias ของผล/หน่วย; ปฏิเสธหน่วยขัดแย้งและหน่วยที่จับคู่ไม่ได้ | `tests/test_domain_units.py` และชุด unit contracts; ไม่แปลงหน่วยโดยเดา |
| Boolean ถูกใช้เป็นตัวเลข | ตรวจ scalar ร่วมกัน รวม NumPy Boolean ในค่าตรวจและ threshold override | regression ของ numeric inputs/thresholds; ค่าตัวเลขและเกณฑ์ทางคลินิกเดิมคงไว้ |
| คะแนนยังไม่สอบเทียบ | แสดงคำอธิบายข้างคะแนนและกราฟ พร้อมสถานะ draft ในรายงาน; เตรียมเครื่องมือเปรียบเทียบ reference cases | ยังต้องมี reference dataset อิสระ, SOP, ผู้ทบทวนและเกณฑ์ยอมรับที่กำหนดล่วงหน้าจากหน่วยงาน |
| ระบุรุ่นโค้ดในรายงานไม่ครบ | เก็บ `build_provenance` ตอนประเมินใน screening, CBC, 6 domains, PCR และ synthetic reporting | `tests/test_build_provenance.py`; การดาวน์โหลดใช้ snapshot เดิม |
| CI และ dependency reproducibility | runtime/development lock ครบ พร้อม hashes; ติดตั้งและตรวจ isolated environment; workflow รวม browser smoke | hosted run และ branch protection ต้องใช้ repository/branch จริง; ไม่อ้างว่าการมี YAML เท่ากับเปิดใช้งานแล้ว |
| หน้าจอจริง/งานพิมพ์ | preview และ download ใช้ HTML ชุดเดียว; Chromium smoke ตรวจ light/dark, desktop/mobile, keyboard, A4 หลายหน้าและข้อความไทย | `scripts/browser_smoke.py`; ผลจริงบันทึกใน `artifacts/browser/evidence.json`; เครื่องพิมพ์จริงและ human UAT แยกต่างหาก |
| บริบทและร่างงานหาย | บทเรียนคงตัวเลือกเมื่อสลับหน้า; เพิ่ม download/import ร่างงานสมมติ JSON | `tests/test_synthetic_drafts.py`; ครอบคลุม report designer/บทเรียน ไม่ใช่ฐานข้อมูลผู้ป่วย |
| Metadata กระจาย | group/icon/tone/short_name ของโมดูลอยู่ใน `data/modules.json` และผ่าน registry validation | `tests/test_platform.py`, `tests/test_navigation.py`; คง 4 กลุ่มและลำดับเดิม |

## การใช้ร่างงานสมมติ

เปิด **อื่นๆ → การออกแบบใบรายงานผล → บันทึกและคืนค่าร่างงานสมมติ (JSON)** แล้วดาวน์โหลดร่างงานหลังแก้ตาราง สามารถอัปโหลดกลับและกดนำเข้าใน session ใหม่ ระบบตรวจข้อมูลทั้งไฟล์ก่อนแทนที่ร่างและคำนวณผลใหม่ ไม่โหลดผลอนุมัติหรือผลประเมินเก่าจากไฟล์

รับเฉพาะ schema ที่กำหนด ไม่เกิน 256 KiB ตรวจ duplicate keys, nonfinite numbers, Boolean ในช่องตัวเลข, รหัส/หน่วยและลำดับรายการตรวจ ไม่ใช้ pickle หรือ serialize session ทั้งก้อน ตัวเลือกบทเรียนและร่างรายงานแต่ละ panel รวมอยู่ในไฟล์ แต่ข้อมูล CBC/PCR/screening/domain ที่กำลังทำอยู่ไม่ถูกเปลี่ยน การระบุ synthetic-only ไม่ใช่การลบข้อมูลระบุตัวบุคคล ห้ามใส่ข้อมูลบุคคลจริงในช่องข้อความ

## ความหมายของ build provenance

`source_sha256` ครอบคลุม Python application source; `lock_sha256` ครอบคลุม runtime/dev lock; `environment_sha256` ระบุ Python/platform/เวอร์ชันแพ็กเกจ runtime ที่ติดตั้งจริง; `build_id` รวมข้อมูลเหล่านี้ กฎที่ใช้ยังมี ruleset hash ของตนเอง Metadata ถูกคัดลอกเข้า result ตอนประเมิน การส่งออกไม่สร้างเวลา/รุ่นโค้ดใหม่ให้ผลเดิม

ลายนิ้วมือนี้เป็นหลักฐานระบุ snapshot ของ workspace ไม่ใช่ลายเซ็นดิจิทัลหรือการป้องกันการแก้ไขโดยผู้ดูแลเครื่อง รีสตาร์ตแอปหลังแก้โค้ดหรือติดตั้งแพ็กเกจ เพื่อให้โค้ดที่โหลดอยู่ตรงกับไฟล์รุ่นใหม่ ไม่ใช้งานหลายรุ่นปะปนใน process เดียว

## การทดสอบภาพจริง

```powershell
.\scripts\setup.ps1 -Dev
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts/browser_smoke.py
```

สคริปต์เปิด server เฉพาะ loopback และ Chromium headless ของตนเอง ไม่ใช้ profile ของผู้ใช้ เก็บ screenshot, HTML/PDF สมมติ, PNG ของแต่ละหน้า และผลตรวจใน `artifacts/browser/` พร้อมปิดเฉพาะ process ที่ตนเริ่ม เอกสาร PDF เป็นผลทดสอบ browser print ไม่ใช่การเพิ่มบริการ PDF ที่ได้รับการรับรอง

ตรวจ actual computed theme, ความกว้างที่ไม่ล้นหน้า, ไม่มี sidebar/error, keyboard เปิดเมนูและหน้า report, preview ตรงกับ HTML ดาวน์โหลด, A4 ทุกหน้า และรายการตรวจ/ข้อความไทยไม่หาย จากนั้นต้องดูภาพ PNG เพื่อตรวจการตัดข้อความและลักษณะ glyph; text extraction อย่างเดียวไม่เพียงพอ แนวทาง API: [Playwright Python](https://playwright.dev/python/docs/library)

ผลรอบนี้ผ่าน light/dark ทั้ง desktop/mobile และการดาวน์โหลด–รีโหลด–นำเข้าร่างงานจริง พร้อมตรวจภาพ PDF หลังปรับ pagination ครบ 8 หน้า (CBC 3 หน้า และ combined 5 หน้า) ใน `artifacts/browser-review/` พบว่า text extraction อาจซ้ำสระ/วรรณยุกต์ไทยแม้ภาพแสดงถูกต้อง จึงใช้ภาพทุกหน้าประกอบการตรวจ การทดสอบ keyboard ยืนยันการเข้าถึงหน้าเป้าหมาย ยังไม่ใช่การรับรองลำดับ focus หรือ screen reader ทั้งระบบ

## สิ่งที่ไม่สามารถรับรองแทนหน่วยงานได้

- ผล clinical validation และการอนุมัติ SOP ต้องมาจากผู้รับผิดชอบและชุดอ้างอิงอิสระจริง โปรแกรมยังไม่อนุมัติผลเพื่อดูแลผู้ป่วย
- Hosted CI/required check ต้องเปิดใน repository เป้าหมายและมีหลักฐาน failed PR ถูกบล็อกจริง ใช้ขั้นตอนใน `CI_SETUP.md`
- การทดสอบเครื่องพิมพ์จริง การใช้ screen reader และ human clinical acceptance ต้องบันทึกแยกจาก automated browser smoke

ผลทดสอบรุ่นล่าสุดและข้อจำกัดที่ตรวจได้จริงอยู่ใน `TEST_RESULTS.md` ห้ามใช้จำนวน tests หรือ coverage เป็นค่าความแม่นยำทางคลินิก

## เปรียบเทียบกรณีอ้างอิงแบบ offline

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_reference_cases.py --write-demo artifacts/reference-demo.json
.\.venv\Scripts\python.exe scripts/evaluate_reference_cases.py artifacts/reference-demo.json --output artifacts/reference-demo-evaluation.json
```

ตัวอย่างที่สร้างเป็น synthetic เท่านั้น สำหรับข้อมูลอ้างอิงจริงให้ผู้รับผิดชอบกำหนด reference standard, labels อิสระจาก engine, case IDs ที่ไม่ระบุตัวบุคคล และ expected endpoints ไว้ก่อนรัน จากนั้นใช้ schema เดียวกันกับ `provenance.kind=independent_reference` การตั้งค่านี้เป็นคำประกาศแหล่งข้อมูล ไม่ใช่หลักฐานว่าผ่านการรับรองแล้ว

เครื่องมือเก็บ observed/expected, จำนวนตรง/ไม่ตรง, confusion counts แยก endpoint และ build/ruleset hashes โดยไม่คัดลอก raw inputs ออกมา ค่า `clinical_approval` คงเป็น false และไม่มีเกณฑ์ผ่านที่ผู้พัฒนาสมมติขึ้น กำหนดประชากร เครื่องมือ กลุ่มย่อย ขนาดตัวอย่าง เกณฑ์ยอมรับและการอนุมัติร่วมกับผู้ทบทวนก่อนประเมินจริง ไม่ใช้ตัวอย่าง synthetic เป็นผล clinical validation
