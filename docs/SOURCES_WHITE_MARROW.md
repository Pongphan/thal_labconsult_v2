# ขอบเขตและแหล่งอ้างอิง: เม็ดเลือดขาวและไขกระดูก

ทบทวนสำหรับต้นแบบวันที่ 8 ตุลาคม 2026 โมดูลทั้งสองมีสถานะ `draft_requires_local_validation` ผลเป็นหลักฐานและเส้นทางตรวจยืนยัน ไม่ใช่ผลวินิจฉัยหรือคำสั่งรักษา ต้องตรวจทานกฎกับ SOP และบริบทจริงก่อนใช้ทางคลินิก

## เม็ดเลือดขาว

`analyze_white_cells(data)` คำนวณ absolute differential จาก WBC × เปอร์เซ็นต์ / 100 โดย neutrophils ต้องรวม bands และไม่ทับซ้อนกับ IG/blasts ค่าที่ห้องปฏิบัติการรายงานมีลำดับก่อนค่าคำนวณ แต่แสดงทั้งสองค่าและเตือนเมื่อขัดแย้ง ข้อมูลที่ขาดไม่เป็นศูนย์ และผลรวม differential ที่ไม่สอดคล้องจะระงับค่าที่คำนวณ

การตรวจผลรวม absolute ใช้หนึ่งค่าต่อชนิดเซลล์ โดยรวมค่าวัดกับค่าคำนวณที่เหลือและ IG/blasts ที่ระบุ จึงตรวจพบกรณี WBC 4, ANC วัด 3 และ lymphocytes 75% ที่ได้ผลรวม 6 ถ้าระบุไม่ครบ ผลรวมเป็นเพียงขั้นต่ำและตรวจว่าไม่เกิน WBC ภายใน tolerance; ถ้าครบทั้งเจ็ดกลุ่ม ผลรวมต้องตรงกับ WBC ภายใน tolerance ทั้งด้านมากกว่าและน้อยกว่า รายงานเก็บองค์ประกอบ แหล่งค่า ความครบถ้วน และ tolerance ใน `calculated.absolute_total` ข้อเตือน ANC/ไข้/blast อิสระยังแสดงแม้ข้อมูลขัดแย้ง

การจัดต่ำ/สูงของจำนวนเซลล์ใช้ช่วงอ้างอิงที่ผู้ใช้ระบุเท่านั้น เกณฑ์ต้นแบบ ANC <0.5 ×10^9/L ใช้ประกอบการทบทวนในผู้ใหญ่อายุอย่างน้อย 18 ปี เมื่อมีหลักฐานไข้ร่วมด้วยจะแจ้งให้ทีมรักษาประเมินโดยเร็ว ไม่ใช่เกณฑ์รับรองการรักษานอกโรงพยาบาล เด็กหรืออายุไม่ทราบคงคำเตือนที่ไม่จัดระดับตามเกณฑ์ผู้ใหญ่ อ้างอิง [MSD Manual: Neutropenia, ปรับปรุงเมษายน 2026](https://www.msdmanuals.com/professional/hematology-and-oncology/leukopenias/neutropenia)

นิยามไข้ต้นแบบใช้การวัดทางปาก ≥38.3°C หนึ่งครั้ง หรือผู้ตรวจยืนยัน ≥38.0°C ต่อเนื่องอย่างน้อย 1 ชั่วโมง ตาม [ASCO/IDSA guideline](https://www.idsociety.org/globalassets/idsa/practice-guidelines/outpatient-management-of-fever-and-neutropenia.pdf) เอกสารเดิมมีบริบทผู้ใหญ่ที่รักษามะเร็ง ระบบใช้เพียงสัญญาณให้ประเมิน ไม่อนุมานการติดเชื้อหรือเสนอการรักษา

ตัวหารเปอร์เซ็นต์ `differential_total=100` และนิยามช่อง `fever_38_for_hour` ที่ผูกกับ 38.0°C/1 ชั่วโมงถูกตรวจเป็นค่าคงที่ หากต้องเปลี่ยนความหมายต้องแก้แบบฟอร์มและตรรกะด้วย ค่า tolerance ของผลรวมและความต่าง absolute เป็นค่าตรวจความสอดคล้องทางเทคนิคของต้นแบบ ไม่ใช่เกณฑ์โรค ค่าทั้งหมดที่ใช้จริงอยู่ในรายงาน `thresholds_used`

## ไขกระดูกและหลักฐานโรคทางโลหิตวิทยา

`analyze_marrow_malignancies(data)` เก็บผลเลือด/ไขกระดูก morphology, flow, molecular, monoclonal protein, ชิ้นเนื้อ และอวัยวะที่มีข้อมูลจริง พร้อมแสดงรายการที่ยังไม่ประเมิน แต่ละกลุ่มสมมติฐานเก็บหลักฐานสนับสนุนและเส้นทางตรวจยืนยัน การไม่มีผลตรวจไม่เป็นผลลบ

- การบูรณาการ morphology, immunophenotype และพันธุกรรมอ้างอิง [CAP/ASH Initial Diagnostic Workup of Acute Leukemia](https://www.cap.org/cap-guidelines/initial-diagnostic-workup-of-acute-leukemia/) และ [ARUP AML, ปรับปรุงมกราคม 2026](https://arupconsult.com/content/acute-myeloid-leukemia)
- PML::RARA ที่รายงานตรวจพบ หรือ morphology สงสัย APL ทำให้เกิดคำเตือนเร่งด่วนโดยไม่รอ blast cutoff; ผล PML::RARA ไม่พบไม่ลบล้าง morphology ที่สงสัย อ้างอิง [European LeukemiaNet APL recommendations](https://ashpublications.org/blood/article/133/15/1630/273295/Management-of-acute-promyelocytic-leukemia-updated)
- เกณฑ์ blasts ปริมาณสูงเริ่มต้น 20% ใช้แจ้งให้ทบทวนเท่านั้น ไม่ใช่ตัวจำแนก AML กลุ่มพันธุกรรมถูกทบทวนได้ต่ำกว่า 20% และผล marrow blasts อาจเทียบกับขอบเขตบนเฉพาะที่ผู้ตรวจระบุ การจำแนกจริงขึ้นกับเกณฑ์และบริบทหลายรายการตาม [WHO fifth edition](https://www.nature.com/articles/s41375-022-01613-1) และ [ICC](https://doi.org/10.1182/blood.2022015850)
- BCR::ABL1 ไม่ถูกใช้แทนคำวินิจฉัย CML ทุกกรณี และ JAK2/CALR/MPL ไม่ยืนยัน MPN subtype โดยลำพัง อ้างอิง [ARUP CML](https://arupconsult.com/content/chronic-myelogenous-leukemia) และ [ARUP MPN](https://arupconsult.com/content/myeloproliferative-neoplasms)
- Monoclonal protein, plasma-cell percentage และ organ findings ไม่ถูกนำไปวินิจฉัย myeloma อัตโนมัติ ต้องบูรณาการ clonality และความสัมพันธ์ของอวัยวะกับโรค อ้างอิง [IMWG criteria](https://www.myeloma.org/international-myeloma-working-group-imwg-criteria-diagnosis-multiple-myeloma)

ไฟล์ `data/white_cells_rules.json` และ `data/marrow_malignancies_rules.json` เก็บแบบฟอร์ม ขอบเขตตรวจข้อมูล เกณฑ์ ข้อความภาษาไทย และแหล่งอ้างอิง ไม่มีการรันโค้ดจากไฟล์กฎ รายงานเก็บรุ่น/hash ของกฎ ค่าที่ใช้จริง และหลักฐานที่ผ่านการตรวจรูปแบบแล้ว ข้อมูลนอกแบบฟอร์มถูกตัดออก
