# Changelog

## 2026-10-16 — Report preview iframe compatibility fix

- Route report preview through the shared Streamlit compatibility helper. Pass native `alt` only when the installed iframe API accepts it; otherwise render the description as an adjacent caption. Preserve the HTML, sizing, keyboard focus and report downloads.
- Reproduce the reported unsupported-`alt` exception with a legacy-signature AppTest, then verify the fix alongside modern-signature, report-layout and synthetic-draft tests. The project's pinned runtime remains unchanged.

## 2026-10-16 — Review remediation, reproducible builds and browser verification

- Preserve and validate domain CSV unit declarations; normalize measurement/unit aliases together; reject conflicting or orphan unit metadata and NumPy Boolean values in numeric fields/threshold overrides. Clinical numerical thresholds are unchanged.
- Capture source/build/environment fingerprints with evaluations across screening, CBC, domains, PCR and synthetic reporting; exports reuse the evaluated snapshot. Content hashing detects edits even when file size/mtime are preserved. HTML rendering verifies snapshot integrity and uses the captured header.
- Display draft/uncalibrated score status beside results and graphs. Add an offline reference-label agreement evaluator with independent-label provenance declarations; it never grants clinical approval or invents acceptance limits.
- Persist learning choices and allow explicit save/restore of versioned synthetic report/learning drafts. Validate whole files before restoration and rerun current validation; no arbitrary session or patient-result import.
- Centralize module group/icon/tone/short name metadata in the catalog. Share one HTML document between report preview and download, and correct the brand spacing under the native toolbar.
- Lock complete runtime/development dependency closures with artifact hashes, verify a fresh install and wrong-hash rejection, and include real Chromium layout/keyboard/draft/PDF checks in CI. Hosted checks and repository protection still require a supplied repository and actual activation evidence.
- Details and operational boundaries: `docs/REVIEW_FIXES.md`; executed results: `docs/TEST_RESULTS.md`.

## 2026-10-16 — Synthetic report designer and implementation specification

- Add `pages/10_Reporting.py` as a reporting utility under Other while preserving the eight clinical-learning modules and the AI placeholder.
- Add six synthetic panel layouts, Thai/English/bilingual report labels, configurable A4 draft layout, editable synthetic measurements, live deterministic validation and HTML/template/validation JSON exports. Every artifact remains a synthetic unsigned draft; there is no clinical release, real-patient ingestion, PDF service or print queue.
- Correct the supplied example: calculated MCHC is approximately 23.6 g/dL and agrees with the reported value. Index, differential and delta comparisons require explicit simulation tolerances; missing policy always prevents release. RDW-CV is not treated as a fraction bounded at 100 percent.
- Document the production architecture, data model, configurable rule catalog, template/review/printing workflows, security/governance, implementation phases, risks and open assumptions in `docs/REPORTING_DESIGN.md`.

## 2026-10-16 — Workspace selection in the top menu

- Remove the homepage workspace-selection section and its grouped topic cards; retain the overview and learning content.
- Move AI assessment and report design to the top Other menu, directly below morphology/quality. Both use the existing teal/indigo tones and show their planned status without an unavailable page link.

## 2026-10-15 — AI assessment and report-design topic cards

- Add two planned homepage cards under Other, in the row after morphology/quality: การประเมินผลด้วย AI and การออกแบบใบรายงานผล.
- Use distinct teal and indigo tones with the current typography and card sizing. No unavailable route or working AI/report-design feature is implied; live counts remain eight modules and nine workspaces.

## 2026-10-15 — Softer dark cards, larger type and top-only navigation

- Remove sidebar rendering and preserve workspace state through the four top navigation groups. Give popover route buttons their module card colors, including portaled content, and match the home hero to its lavender navigation button.
- Soften dark fills and accents; increase base type from 16 to 20 px and fixed presentation/chart text by 4 px.
- Increase top button minimum heights by 10%. Add intrinsic card-height scaling where supported, with 10% vertical-padding fallback and content-driven growth for long labels.
- Adapt existing navigation regressions to top controls and assert the sidebar stays empty while retaining saved reports and draft inputs.

## 2026-10-15 — Vivid dark theme and four navigation groups

- Brighten dark-mode card fills, accents, borders and native semantic colors; retain eight distinct topic colors and the existing light palette.
- Group the top menu, sidebar and homepage catalog through one shared registry: home, red-cell disorders, white-cell disorders and other topics. Preserve every route and navigation key.
- Show grouped module cards before the learning sections and distinguish the four navigation groups from the eight modules and nine workspaces.

## 2026-10-15 — Cross-module safety, rule review package and CI

- Share demographic threshold-context validation across screening/CBC. Withhold dependent cutoffs for unresolved context; reject explicit conflicts and unsupported context. Invalid screening classification flags are now null, while independent valid low-Hb alerts remain visible. Reject NumPy booleans as CBC numbers.
- Preserve CBC demo lineage, report ID/time/rule hash, copied values and units in downstream source snapshots. Check source validity and unit/type compatibility before mutating destination state.
- Support optional explicit unit declarations for CBC/screening API and screening CSV imports; reject mismatches without guessing conversions and retain rejected strings for review. Mixed-row DataFrame missing optional metadata preserves valid urgent Hb observations. Warn when retained screening results refer to a changed/removed CSV.
- Add conservative multi-group findings, uncertainty and next-action ownership, with clinician/patient draft wording and policy provenance. Existing valid scores, patterns and numerical cutoffs are unchanged. JSON schema 2 additions are backward-compatible; invalid classification nulls are an intentional safety correction.
- Add pytest regression/boundary suites, 80% application statement/branch coverage gate, lint, rule-inventory stale check, GitHub workflow and required-check payload. Full local suite: 1,457 passed, coverage 93.20%; hosted activation awaits repository details.
- Deliver 999-entry rule review inventory, expert review questions, 24-case UAT plan, sign-off templates and implementation traceability. All clinical/UAT approvals remain pending.

## 2026-10-15 — WBC totals, durable drafts and complete reports

- Validate the sum of one effective count per WBC population, combining measured and derived values and including reported IG/blasts. Missing categories remain unknown. Impossible sums retain independent ANC/fever and blast alerts. Expose total components, tolerance and completeness for review.
- Withhold adult female sex/pregnancy-dependent Hb/Hct interpretation when pregnancy is unknown. Preserve age-only childhood rules and independent low-Hb observations. Numeric clinical cutoffs are unchanged.
- Preserve CBC, screening, PCR and shared-domain draft inputs across navigation. CBC/screening/domain evaluation remains explicit; prior report snapshots remain stable until reassessment. PCR keeps its clearly labelled live results. Retain uploaded CSVs in session memory, with explicit removal and scoped reset.
- Export screening JSON schema version 2 with complete nested thresholds, partner screening and native lists, while retaining prior top-level input aliases. CSV now includes all partner fields and input origin. Domain batch reporting rejects mismatched result/metadata lengths rather than dropping rows.
- Extend the pastel learning-lab homepage with a WBC balance visualization: absolute measured/calculated components, an explicit WBC reference and an unexplained remainder. Three synthetic scenarios use the same WBC engine without modifying workspace results.
- Add a Thai user acceptance kit with six tasks, expected outcomes, observation forms and retest criteria. Actual user testing remains pending at the user's request; no human feedback is fabricated.
- Refresh ZIP, SHA-256 manifest and readable source together from one allowlisted snapshot. See `docs/TEST_RESULTS.md` for executed checks and their limitations.

## 2026-10-14 — Local learning release and hematology workspace redesign

### Fixed

- Validate both resolved and combined Hb-fraction totals, including incomplete resolved pairs, without double-counting overlapping peaks. Contradictory totals no longer bypass validation through the other representation.
- Withhold age-dependent CBC and HbA2/HbF interpretation when age is missing. Unknown adult sex no longer selects female Hb/Hct thresholds implicitly; unavailable effective thresholds serialize as `null`. Usable urgent-Hb observations remain visible despite other invalid or incomplete inputs. Numeric threshold values were not changed; screening rules metadata is now `2026.10-review-2` to identify the changed input policy.
- Share strict CSV validation across screening, PCR and domain workspaces. Reject duplicate/alias-equivalent headers, malformed row widths and oversized inputs before discarding unsupported columns. Preserve blank rows for explicit review and apply the 2 MB / 200-row limits consistently.
- Load screening rules and calculate the rule hash once per batch. Preserve evaluation timestamps and rule snapshots across screening CSV, JSON, Markdown and batch exports.
- Repair the moved local `.venv` launchers with the existing CPython 3.12.15 interpreter while preserving installed packages.

### Changed

- Adapt the header, navigation and task-card layout from `parasitic_platform_2027` to a pastel hematology palette. Use compact workspace headers and flat tinted cards, with application-scoped CSS and native form, warning, table and chart surfaces.
- Make the homepage eight-module learning map and example-count bar chart visible by default, with a selector and workspace links. Counts come from bundled synthetic examples; visuals do not represent disease prevalence or clinical severity.
- Define the release scope as learning and review on one local computer, with loopback-only launch and Streamlit usage telemetry disabled. Clinical rules remain drafts; the phenotype-similarity demonstration was not trained or clinically validated by this release.

### Added

- Windows launch/setup/check/test scripts and an exact 39-package Windows/Python 3.12 dependency snapshot. Local setup documentation covers environment relocation, version verification and fresh installation requirements.
- A rule-review template recording scope, sources, independent expected results and unresolved findings without implying clinical approval.
- A maintained source packager with explicit data/documentation allowlists, deterministic archive contents and SHA-256 file manifests. It packages the current working tree without changing Git state; its default mode writes no artifacts.
- Software verification: **182 tests passed**, plus **22 dark-branch UI tests**. Headless/chart/contrast checks and a healthy loopback server were verified; actual desktop/mobile browser screenshots were unavailable. Full evidence and limitations are in `docs/TEST_RESULTS.md`.

## 2026-10-08 — Sidebar module cards and readable contrast

### Added

- Compact persistent sidebar cards for all eight module groups, home navigation, separate thalassemia/PCR actions, and an explicit current-page indicator with keyboard focus.
- Native responsive sidebar defaults and two routing regressions covering every destination, report retention, domain input persistence and current-page reruns.

### Changed

- Replaced the main workspace dropdown with sidebar cards. Module details remain in a homepage expander; existing page URLs and clinical state are preserved.
- Strengthened card boundaries, standalone caption text and sidebar colors in both themes while preserving pastel gradients and semantic alert colors.
- Centralized chart typography, hover surfaces, axes and series outlines; PCR plots reuse the shared chart theme. Measurements, chart flows, clinical rules and dependencies are unchanged.

### Removed

- The redundant main-page navigation selector and its unused CSS; no clinical functions or report formats were removed.

## 2026-10-08 — Learning overviews across all modules

### Added

- Thai learning content for all eight module groups, with three-step overviews, learning points, limitations, primary-source links and workspace navigation.
- Opt-in synthetic examples for CBC and the six domain engines, showing input units, findings, recommendations, safety messages and rule provenance without writing to clinical forms.
- Editable `data/learning_modules.json` with catalog-coverage and content validation; rendering and example construction are separated into `ui/learning.py` and `utils/learning.py`.

### Changed

- Expanded the homepage learning area into a module selector and three tabs, using each module's pastel palette. Thalassemia remains the default topic and keeps both existing demonstration charts.
- Corrected the spectrum's homozygous-HbE teaching cue and clarified variable phenotypes. Its colors now identify globin groups; removed unsupported severity bands, risk axes and progression lines while preserving all 13 teaching labels and both chart entry points. The six-case Sankey remains unchanged and explicitly describes review tiers.

### Removed

- No working features, clinical rules or dependencies were removed or changed.

## 2026-10-08 — Hematology visual identity and component hierarchy

- Replaced the cool indigo foundation with ruby/plum gradients, warm pearl surfaces, coordinated light/dark controls and eight distinct pastel module palettes.
- Added an accessible static hero with original decorative blood-cell artwork, eight original module icons, numbered category headers, a CBC starting link, and a framed workspace selector/footer.
- Embedded vector art as SVG data-URI images because Streamlit's HTML-only sanitizer removes raw SVG tags; decorative images have empty alt text and need no external image/font requests.
- Refined CBC and domain forms/results into readable numbered steps, aligned field rows and balanced evidence/recommendation panels. Updated PCR headings and chart colors without changing their data.
- Constrained desktop reading width, improved Thai typography and button targets, and hid decorative hero art on narrow screens. Native controls, focus, disabled states and clinical alerts remain available.
- No dependencies or clinical rules changed.

## 2026-10-08 — Platform-wide gradients

- Added coordinated light/dark gradients for the canvas, header, toolbar, module cards, forms, action buttons, tabs, expanders and chart/table frames.
- Each clinical module retains its own two-color pastel gradient; the shared palette centralizes all stops and the limited native frontend selectors.
- Alert overlays retain native severity colors. Disabled buttons and focus/selection indicators retain their native behavior.
- Plotly canvases are transparent over gradient frames; series colors and readable hover-label surfaces remain intact.
- No clinical calculations, dependencies, input handling or report formats changed.

## 2026-10-08 — Modern pastel cards

### Added

- Eight distinct pastel card surfaces, one per clinical module, with matching page introductions and light/dark variants in `ui/palette.py`.
- Shared keyed card component, keyboard focus outlines, subtle hover feedback on module cards, and reduced-motion support.

### Changed

- Updated the complete theme to cool porcelain, indigo and navy; coordinated native controls, badges, tables, callouts and chart colors.
- Grouped input, evidence, result and report sections into colored cards with consistent spacing, rounded corners and soft shadows.
- Scoped custom CSS to documented application-owned `st-key-` classes; native interactive controls and clinical alert semantics remain intact.
- Gave alpha/beta PCR result metrics explicit distinct keys to preserve both result panels on the same page.

### Removed

- Replaced the previous uniform card surfaces. No clinical features, rules, reports or dependencies were removed or added.

## 2026-10-08 — Streamlit 1.60 runtime compatibility

- Use inline Material icons in headings and metric labels instead of newer `icon` parameters; remove the unsupported button `wrap` argument.
- Add an explicit rendering adapter for charts/tables/editors: retain native `alt` on newer Streamlit, or show the same description as an adjacent caption on 1.60. Other arguments and return values remain intact.
- Update partner screening in a form-submit callback so corrected values are reflected in the saved result and reports before rendering, avoiding stale form values on Streamlit 1.60.
- Validate against the user's `penv` runtime (Python 3.13.7, Streamlit 1.60.0, pandas 3.0.3) as well as the project's newer runtime; align dependency bounds with these supported versions.

## 2026-10-08 — Theme configuration compatibility

- Removed `dataframeHeaderTextColor` and `chartCategoricalColors` from the light/dark theme sections because some Streamlit installations reject those variant options.
- Dataframe header text inherits the native theme; existing Plotly helpers retain their explicit pastel palettes. No clinical behavior changed.

## 2026-10-08 — Pastel hematology UI/UX

### Added

- Native light/dark themes with rose, lavender, sage and warm amber accents, Thai system-font fallbacks, and explicit semantic text/background colors
- Compact category badges, clearer workspace entry points, and grouped form/result/report sections

### Changed

- Replaced oversized navigation cards and stacked global style overrides with native Streamlit components
- Reduced heading sizes and visual weight, clarified source/demo states, and moved secondary details into expanders while retaining urgent messages
- Unified chart palettes with the platform theme and preserved existing routes, controls, clinical calculations, session behavior and downloads

### Removed

- Global CSS tied to Streamlit's private DOM selectors and operating-system theme overrides
- No clinical modules, rules or report formats were removed; no dependencies were added

## Complete domain workspaces — Hematologic Platform

### Added

- เพิ่มเครื่องมือใช้งานจริงครบ 6 กลุ่มที่เดิมเป็นแผน: WBC, marrow/malignancies, platelets/bleeding, thrombosis, transfusion และ morphology/quality
- engine, JSON schema/ข้อความ/แหล่งอ้างอิง และกรณีทดสอบแยกทุกกลุ่มงาน
- แบบฟอร์มรายตัวอย่าง, ข้อมูลสมมติ, CSV 2 MB/200 แถว พร้อมแม่แบบและคำอธิบายตัวเลือก
- รายงาน CSV/JSON รายตัวอย่างและรายชุด พร้อมผลคำนวณ ข้อเตือน ขอบเขต และหลักฐานรุ่นกฎ
- การคัดลอกค่าตัวเลขที่หน่วยตรงจาก CBC โดยผู้ใช้เลือก และการล้างข้อมูลแยกกลุ่มงาน
- คู่มือความสามารถปัจจุบันและเอกสารต้นทางของทั้ง 6 กลุ่ม

### Changed

- หน้าหลักแสดงครบ 8 กลุ่ม / 9 พื้นที่ทำงาน ใช้ตัวเลือกนำทางที่รองรับจำนวนหน้ามากขึ้น
- เก็บแบบฟอร์มใน session เมื่อสลับหน้า/โหมด เพื่อไม่ให้ข้อมูลกับที่มาของข้อมูลคลาดกัน
- การตรวจ enum คงค่า `none` ที่เป็นคำตอบจริง; multiselect คงข้อสังเกตที่ใช้ได้เพื่อไม่ให้ข้อเตือนหายเมื่อมีค่าผิดปน
- แสดงหน่วยจาก schema ทั้งแบบฟอร์ม ข้อผิดพลาด และรายงาน
- คงระบบ CBC/ธาลัสซีเมีย/PCR เดิม และ dependencies หลักสี่รายการ

### Removed

- สถานะมีเพียงแผนพัฒนาของ 6 กลุ่มงานที่เพิ่มเครื่องมือแล้ว
- ไม่มีการลบ clinical engine หรือรายงานเดิม

### Clinical scope

- ครบกลุ่มงานในระดับเครื่องมือช่วยทบทวน ไม่ใช่ครอบคลุมทุกโรค/การรักษาหรือผ่าน clinical validation
- ไม่มีการอนุมัติจ่ายเลือด ลงนามรายงาน วินิจฉัยมะเร็งขั้นสุดท้าย หรืออ่านภาพเซลล์อัตโนมัติ

## 2026-10-07 — Hematologic Platform foundation and CBC

### Added

- หน้าศูนย์รวม ThalLink (Hematologic Platform) แบ่ง 8 กลุ่มงาน พร้อมสถานะเปิดทดลอง/แผนพัฒนา
- `data/modules.json` และ registry สำหรับกำหนดชื่อ ขอบเขต และเส้นทางโมดูลจากที่เดียว
- โมดูล CBC/ภาวะโลหิตจางผู้ใหญ่ แยก UI, engine และกฎ JSON; ไม่ใช้เกณฑ์ผู้ใหญ่โดยปริยายในกลุ่มนอกขอบเขต
- ช่วงอ้างอิงผลตรวจประกอบที่ผู้ใช้ระบุ รายงาน CSV/JSON และข้อมูลเกณฑ์ที่ใช้จริง
- เอกสารขอบเขตแพลตฟอร์ม ลำดับการพัฒนา และการทบทวนกฎแยกโมดูล
- การทดสอบ CBC/ขอบเขตประชากร/ช่วงอ้างอิง และการเชื่อมเมนูกับ workflow เดิม

### Changed

- ชื่อและหน้าแรกเป็นแพลตฟอร์มโลหิตวิทยา; ธาลัสซีเมียเป็นโมดูลเฉพาะทางหนึ่งของแพลตฟอร์ม
- ข้อมูลสาธิตและกราฟหน้าแรกเดิมเปิดผ่านตัวเลือกแสดงข้อมูลธาลัสซีเมีย
- Streamlit ขั้นต่ำ 1.65 ตาม API ที่ใช้และสภาพแวดล้อมทดสอบ; ยังคง dependencies หลักสี่รายการ

### Removed

- ไม่ลบกฎหรือความสามารถของระบบธาลัสซีเมีย/PCR เดิม และคงเส้นทางหน้าเดิม

### Scope

- โรคเม็ดเลือดขาว มะเร็งทางโลหิตวิทยา bleeding/thrombosis, transfusion และ morphology เป็นแผนพัฒนา ยังไม่มีระบบวินิจฉัยกลุ่มโรคเหล่านั้น
- กฎ CBC ใหม่เป็นร่างรอทบทวนทางคลินิก ไม่ใช่การรับรองว่าครอบคลุมโรคเลือดทั้งหมด

## 2026-10-07 — Thai screening and molecular review

### Added

- `logic/` แยก engine, validation, rule loader และตัวอย่าง
- JSON ที่ทบทวนได้สำหรับ screening rules และ demonstration allele panel
- ผลภาษาไทย: rationale, unconfirmed genotype candidates, confirmatory tests, counseling, validation, rule version/hash และเกณฑ์ที่ใช้จริง
- CSV ภาษาไทยแบบ UTF-8 BOM พร้อมป้องกัน formula injection; strict JSON ไม่ส่ง NaN
- ช่อง HbH inclusion, OF/NESTROFT method, ประวัติที่ไม่ทราบ และค่าตัวเลขว่าง
- PCR call-sheet import/editor, explicit control gating, conflict review, virtual gel และรายงาน CSV
- unittest และ Streamlit AppTest สำหรับตัวอย่างและข้อผิดพลาดเดิม
- คู่มือทบทวนกฎ วิธีรัน ข้อจำกัด และชุดโค้ดเต็ม

### Changed

- หน้า/ผลคัดกรองและ UI พันธุกรรมเป็นภาษาไทย เก็บ scientific names และ machine-readable keys
- คง single/batch workspaces, Plotly charts, panel browser, couple models, Markdown/JSON/CSV และ ML feature export
- คง import เดิมผ่าน `thalab/core.py` และ `thalab/reporting.py`
- คำเตือน Hb ต่ำรุนแรงไม่ถูกกฎ Hb typing ลบล้าง รวมแถวที่มีข้อมูลอื่นผิดพลาด
- เกณฑ์ MCV/MCH ตามอายุเป็นค่าเริ่มต้น; override ต้องเลือกใช้ชัดเจน
- ใช้ผล engine เดียวกันใน UI และรายงาน; partner assay ที่ใช้ไม่ได้ไม่ลบผลผู้ป่วย
- แยก missing/negative/indeterminate/invalid และ HbA2/HbA2-E
- ระงับกฎ fraction แบบผู้ใหญ่ในเด็กเล็กตามค่าอายุขั้นต่ำในโปรไฟล์
- Punnett รวม genotype ซ้ำและกราฟใช้ probability จริง
- กราฟจำลองไม่สร้างพีคหรือแถบแทนข้อมูลที่ไม่ได้ตรวจ
- CSV import ตัดคอลัมน์ที่ไม่รองรับและแทนรหัสด้วยรหัสสมมติ ไม่มี patient persistence
- Python 3.10+; dependencies หลักสี่รายการ

### Removed

- การใช้ HbA2/E รวมแทน HbA2 ที่แยกวัดโดยอัตโนมัติ
- การสรุป genotype จาก EE score โดยไม่มีข้อกำหนด applicability (ยังมีส่วนอธิบายข้อจำกัด)
- กฎ anemia/ferritin ซ้ำในหน้า UI และการ join batch ด้วย sample ID ที่ทำให้แถวเพิ่มเมื่อ ID ซ้ำ
- `openpyxl` ซึ่งไม่มี workflow ที่ใช้งาน
- คำอ้างว่าชุดกฎ/แผงตรวจสาธิตผ่านการ validation แล้ว

### Assumptions and clinical review

- ใช้โปรไฟล์เริ่มต้นรอผู้เชี่ยวชาญและ SOP สถาบันทบทวน ไม่มีการรับรองวินิจฉัยหรือ release report
- Deployment และจำนวนผู้ใช้พร้อมกันยังไม่ระบุ; ไม่ได้ deploy หรือทำ load test
- บัญชีผู้ใช้ ฐานข้อมูลประวัติ การลงนาม และ LIS/LIMS ยังไม่เพิ่ม เพื่อคงขอบเขตไม่จัดเก็บข้อมูลระบุตัวบุคคล
- ข้อมูลบนหน้าจออยู่ใน session memory; hosting/logging policy ต้องจัดการโดยผู้ดูแล
- รายละเอียดเกณฑ์ อายุ วิธีตรวจ พีคซ้อน และขอบเขต PCR อยู่ใน `docs/CLINICAL_REVIEW.md`
