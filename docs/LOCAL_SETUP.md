# เรียกใช้และตรวจสอบบนเครื่องส่วนตัว

รุ่นนี้ใช้เรียนรู้และทบทวนผลภายในเครื่องเดียว ข้อมูลอยู่ใน session ไม่มีบัญชีผู้ใช้ ฐานข้อมูลผู้ป่วย การลงนาม หรือการเชื่อม LIS/LIMS การตั้งค่าเริ่มต้นและ launcher ผูกกับ `127.0.0.1` และปิด usage telemetry ของ Streamlit

## เปิดบน Windows

ดับเบิลคลิก `run.cmd` แล้วเปิด `http://127.0.0.1:8501` หยุดด้วย `Ctrl+C` ในหน้าต่างที่รันแอป หากใช้พอร์ตนี้อยู่แล้ว:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Port 8507
```

`run.cmd` ใช้ execution policy เฉพาะโปรเซสที่เปิดสคริปต์ ไม่เปลี่ยนนโยบายของเครื่องหรือบัญชีผู้ใช้ สคริปต์หาโฟลเดอร์จากตำแหน่งของตัวเอง จึงเรียกจากโฟลเดอร์อื่นได้ และใช้ `.venv\Scripts\python.exe -m streamlit` เพื่อหลีกเลี่ยง console launcher ที่อาจยังอ้างพาธเดิม

หากพบ `IframeMixin.iframe() got an unexpected keyword argument 'alt'` ให้ใช้โค้ดล่าสุดและรีสตาร์ตแอป ตัวช่วยแสดงรายงานจะตรวจว่ารองรับ `alt` ก่อนส่งค่า และแสดงคำอธิบายข้างรายงานเมื่อไม่รองรับ หาก traceback อ้าง `Python314\Lib\site-packages` แทน `.venv\Lib\site-packages` แสดงว่ากำลังใช้ Python อีกชุดหนึ่ง ให้หยุด process เดิมแล้วเปิดด้วย `run.cmd` เพื่อใช้ environment ของโครงการที่ผ่านการตรวจเวอร์ชัน

## ติดตั้งใหม่

ใช้ CPython 3.12 แบบ 64 บิต สำหรับชุดเวอร์ชันที่ล็อกไว้ (ทดสอบจริงด้วย 3.12.15):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

หากไม่มี Python launcher `py` ให้ระบุ interpreter:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Python C:\Python312\python.exe
```

สคริปต์สร้าง `.venv` เฉพาะเมื่อยังไม่มี ตรวจเวอร์ชันและ application imports และติดตั้งจาก `requirements-lock-win-py312.txt` เฉพาะเมื่อ dependencies ยังไม่ตรง ไฟล์นี้ล็อก dependencies ต่อเนื่องทั้งหมด 39 packages ของแอป ส่วน `-Dev` ใช้ `requirements-dev-lock-win-py312.txt` ซึ่งรวม runtime และเครื่องมือทดสอบครบ 52 packages เมื่อเวอร์ชันตรงและ imports ผ่าน สคริปต์จะไม่เรียกตัวติดตั้งหรือใช้เครือข่าย

การติดตั้งใหม่ต้องเข้าถึง package index หรือมีแพ็กเกจในแหล่งติดตั้งที่ผู้ใช้กำหนดไว้ ทั้งสอง lock มี SHA-256 ของ artifacts จาก PyPI; setup และ CI บังคับ `--require-hashes --only-binary=:all:` จึงปฏิเสธไฟล์ที่ hash ไม่ตรงและไม่ build source distributions ตัว lock ผูกกับ Windows x86_64/Python 3.12; hashes ยืนยันว่าไฟล์ที่ติดตั้งตรงกับรายการที่ทบทวน ไม่ใช่การรับรองความปลอดภัยของแพ็กเกจ และการตรวจ environment ที่ติดตั้งแล้วตรวจ metadata/imports ไม่ได้ตรวจ hash ของทุก installed file

ขั้นต่ำของแอปคือ Streamlit 1.65 เนื่องจากใช้ native `st.iframe` ใน report preview; ชุดที่ล็อกยังเป็น 1.65.0 โดยไม่ได้อัปเกรด runtime packages ในรอบแก้ไขนี้

สำหรับ Linux/macOS หรือ Python รุ่นอื่น ให้สร้าง environment แยก ติดตั้ง `requirements.txt` และรันทดสอบทั้งหมด การผ่านบน Windows ในรุ่นนี้ไม่ได้ยืนยันแพลตฟอร์มอื่นโดยอัตโนมัติ:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/check_environment.py
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/python -m streamlit run app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
```

## ตรวจ environment และทดสอบ

ชุดทดสอบเต็มใช้ pytest เพื่อรวมทั้ง unittest เดิมและ parameterized tests ใหม่ ติดตั้งเครื่องมือพัฒนาครั้งแรกด้วย `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Dev` แล้วใช้ `scripts/test.ps1` ซึ่งตรวจ lint, inventory และ coverage ด้วย ดู [CI_SETUP.md](CI_SETUP.md)

```powershell
.venv\Scripts\python.exe -X utf8 scripts/check_environment.py --locked
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

ตัวตรวจตรวจทั้ง direct/transitive dependency constraints, requested extras และ imports หลัก; `--locked --development` ตรวจเวอร์ชันตรงทุก package ใน dev lock และปฏิเสธ dependency ที่ไม่มีใน lock หากต้องแยกปัญหา runtime ออกจากกฎของแอป ใช้ `--dependencies-only` ชุดทดสอบใช้ pytest ร่วมกับ unittest และ Streamlit AppTest

Browser/PDF QA ใช้ Playwright และ pypdfium2 จาก dev lock และ Chromium revision ที่มากับ Playwright รุ่นที่ pin ไว้ ต้องติดตั้ง browser แยกครั้งแรก (browser binary ไม่อยู่ใน Python wheel lock):

```powershell
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe scripts/browser_smoke.py
```

สคริปต์เปิดเฉพาะ test server บน localhost และใช้ข้อมูลสังเคราะห์ เก็บภาพ, PDF และ evidence ใน `artifacts/browser/` ไม่ใช้ browser profile ของผู้ใช้ ผลนี้ตรวจ software rendering ไม่ใช่การรับรองเครื่องพิมพ์จริงหรือผลตรวจทางคลินิก

## เมื่อย้ายโฟลเดอร์แล้ว Python เปิดไม่ได้

Virtual environment ไม่ใช่ส่วนที่พกพาข้ามเครื่องได้เสมอ กรณี workspace นี้เดิมย้ายจากพาธ `D:\P Works\...` ทำให้ทั้ง `pyvenv.cfg` และ uv launcher อ้างตำแหน่งเดิม ได้ซ่อม launcher โดยใช้ Python 3.12.15 ที่มีอยู่ใน `.tools` และเก็บ packages เดิมทั้งหมด ไม่มีการดาวน์โหลดหรืออัปเกรด packages

`setup.ps1` รองรับการซ่อมกรณีเดียวกันเมื่อยังมี `.tools\uv\uv.exe` และ `.tools\python\cpython-3.12.15-windows-x86_64-none\python.exe` โดยใช้ `uv venv --allow-existing --offline --no-python-downloads` ไม่ล้างโฟลเดอร์ ไม่ซ่อม environment ที่เปิดได้แต่เป็น Python คนละรุ่นโดยอัตโนมัติ

หากไม่มีเครื่องมือภายในดังกล่าว ให้ปิดแอป เก็บสำเนา `.venv` เดิมในชื่ออื่นด้วย File Explorer แล้วรัน setup ใหม่จาก CPython 3.12 ไม่ต้องแก้ไฟล์ executable หรือสร้าง symbolic link กลับไปพาธเก่า

## อัปเดตและส่งต่อ

1. หยุดแอปและเก็บงานที่ต้องการส่งออกก่อนเปลี่ยนโค้ดหรือ environment; session จะเริ่มใหม่เมื่อรีสตาร์ต
2. เก็บ source, JSON rules, `requirements.txt` และ lockfile ไปด้วยกัน; ไม่ส่ง `.venv`, `.tools`, secrets หรือข้อมูลจากผู้ป่วย
3. หลังอัปเดต dependencies ให้สร้าง environment ใหม่ ทบทวนข้อเปลี่ยนแปลงของแพ็กเกจ regenerate ทั้ง runtime/dev locks พร้อม hashes ตาม [CI_SETUP.md](CI_SETUP.md) แล้วรันทดสอบและตรวจหน้าจอจริงก่อนใช้ต่อ ห้ามเติม hash ที่คาดเดาหรือปิด `--require-hashes` เพื่อให้ติดตั้งผ่าน
4. บันทึกเวอร์ชัน Python/แพ็กเกจและผลตรวจใน `TEST_RESULTS.md` แยก software verification ออกจากการทบทวนทางคลินิก

การเผยแพร่ผ่าน LAN/อินเทอร์เน็ตอยู่นอกขอบเขตรุ่นนี้ การเปลี่ยนไปใช้หลายคนหรืองานบริการต้องประเมินรูปแบบสิทธิ์เข้าถึง การเก็บข้อมูลและการรับรองกฎตามบริบทใหม่ก่อน

## สร้าง source snapshot

```powershell
.venv\Scripts\python.exe scripts/package_source.py
.venv\Scripts\python.exe scripts/package_source.py --build
```

คำสั่งแรกตรวจรายการไฟล์โดยไม่เขียน artifact คำสั่งที่สองสร้าง `deliverables/thal_labconsult_source.zip` และ `deliverables/SOURCE_MANIFEST.json` พร้อม SHA-256 รายไฟล์ โดยอ่าน source จาก working tree ปัจจุบัน ไม่แก้ Git index และไม่อาศัยว่าไฟล์ถูก commit แล้วหรือยัง

ตัว packager รวม source, scripts, lockfile, launchers, กฎ และไฟล์ตัวอย่าง/เอกสารตาม allowlist ที่กำหนด ไม่รวม environment, `.tools`, secrets, ไฟล์ดาวน์โหลดรายงาน หรือ CSV อื่นที่เพิ่มเข้ามา ตรวจ manifest ก่อนส่งต่อเสมอ เมื่อเพิ่มไฟล์กฎ ตัวอย่าง หรือเอกสารใหม่ ให้เพิ่มใน allowlist ของ `scripts/package_source.py` โดยตั้งใจ `SOURCE_MANIFEST.json` เป็นหลักฐานว่าชุดไฟล์ตรงกัน ไม่ใช่ลายเซ็นดิจิทัลหรือการรับรองทางคลินิก
