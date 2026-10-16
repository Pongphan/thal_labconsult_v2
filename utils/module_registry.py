"""Read the platform catalog; module availability is distinct from clinical approval."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "modules.json"
STATUS_LABELS = {"draft": "เปิดทดลอง · รอทบทวนทางคลินิก", "planned": "อยู่ในแผนพัฒนา"}
PLATFORM_DISCLAIMER = (
    "ThalLink เป็นแพลตฟอร์มสนับสนุนการคัดกรองและทบทวนผลทางโลหิตวิทยา "
    "ไม่ใช่การวินิจฉัยโรค ผลเป็นร่างที่ต้องให้ผู้ประกอบวิชาชีพทบทวนตามบริบทและ SOP ของหน่วยงาน "
    "แต่ละโมดูลมีขอบเขตเฉพาะและยังต้องตรวจสอบความใช้ได้ทางคลินิก"
)


@dataclass(frozen=True)
class PageSpec:
    key: str
    title: str
    path: str
    icon: str
    caption: str
    badge: str


REPORT_DESIGN_PAGE = PageSpec(
    key="Report design", title="การออกแบบใบรายงานผล", path="pages/10_Reporting.py",
    icon=":material/description:", caption="ออกแบบและตรวจสอบรายงานต้นแบบด้วยข้อมูลสมมติ",
    badge="ต้นแบบข้อมูลสมมติ",
)


@dataclass(frozen=True)
class PresentationSpec:
    group: str
    icon: str
    tone: str
    short_name: str


UTILITY_PRESENTATION = MappingProxyType({
    "ai_assessment": PresentationSpec("other", ":material/psychology:", "teal", "AI assessment"),
    "report_designer": PresentationSpec("other", ":material/description:", "indigo", "Report design"),
})


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    title: str
    status: str
    summary: str
    scope: str
    planned_scope: str
    presentation: PresentationSpec
    routes: tuple[PageSpec, ...]


@dataclass(frozen=True)
class NavigationGroup:
    """One navigation category, including optional nonclinical utility pages."""

    id: str
    title: str
    icon: str
    tone: str
    modules: tuple[ModuleSpec, ...]
    pages: tuple[PageSpec, ...]


def load_modules(path: Path = CATALOG_PATH) -> tuple[ModuleSpec, ...]:
    """Validate reference metadata; never execute code named by catalog contents."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError("ไม่สามารถอ่านรายการโมดูลของแพลตฟอร์ม") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("รูปแบบรายการโมดูลไม่รองรับ")
    rows = payload.get("modules")
    if not isinstance(rows, list) or not rows:
        raise ValueError("รายการโมดูลต้องเป็นรายการที่ไม่ว่าง")
    modules: list[ModuleSpec] = []
    module_ids: set[str] = set()
    route_keys: set[str] = {"Command center", REPORT_DESIGN_PAGE.key}
    route_paths: set[str] = {"app.py", REPORT_DESIGN_PAGE.path}
    for item in rows:
        text_fields = ("id", "title", "status", "summary", "scope", "planned_scope")
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip() for key in text_fields
        ):
            raise ValueError("ข้อมูลชื่อ ขอบเขต หรือสถานะโมดูลไม่ครบถ้วน")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", item["id"]) or item["id"] in module_ids or item["id"] in UTILITY_PRESENTATION:
            raise ValueError("รหัสโมดูลไม่ถูกต้องหรือซ้ำกัน")
        if item["status"] not in STATUS_LABELS:
            raise ValueError("สถานะโมดูลไม่รองรับ")
        presentation = item.get("presentation")
        if not isinstance(presentation, dict) or set(presentation) != {"group", "icon", "tone", "short_name"}:
            raise ValueError("ข้อมูลการแสดงผลโมดูลไม่ครบถ้วน")
        if any(not isinstance(value, str) or not value.strip() for value in presentation.values()):
            raise ValueError("ข้อมูลการแสดงผลโมดูลต้องเป็นข้อความที่ไม่ว่าง")
        if presentation["group"] not in {"red_cells", "white_cells", "other"}:
            raise ValueError("กลุ่มโมดูลไม่อยู่ในสามหมวดงานที่กำหนด")
        if not re.fullmatch(r":material/[a-z0-9_]+:", presentation["icon"]):
            raise ValueError("ไอคอนโมดูลต้องเป็น Material icon ที่กำหนด")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", presentation["tone"]) or len(presentation["short_name"]) > 70:
            raise ValueError("ชื่อสีหรือชื่อย่อโมดูลไม่ถูกต้อง")
        routes = item.get("routes")
        if not isinstance(routes, list) or (item["status"] == "planned" and routes):
            raise ValueError("โมดูลในแผนพัฒนาต้องไม่มีลิงก์เปิดแปลผล")
        if item["status"] == "draft" and not routes:
            raise ValueError("โมดูลเปิดทดลองต้องมีหน้าที่เข้าใช้งานได้")
        pages: list[PageSpec] = []
        for route in routes:
            keys = ("key", "title", "path", "icon", "caption", "badge")
            if not isinstance(route, dict) or any(
                not isinstance(route.get(key), str) or not route[key].strip() for key in keys
            ):
                raise ValueError("ข้อมูลหน้าโมดูลไม่ครบถ้วน")
            route_path = PurePosixPath(route["path"])
            if (
                len(route_path.parts) != 2 or route_path.parts[0] != "pages"
                or route_path.suffix != ".py" or "\\" in route["path"]
                or ":" in route["path"] or route_path.as_posix() != route["path"]
            ):
                raise ValueError("หน้าโมดูลต้องเป็นไฟล์ Python ภายใน pages/")
            if route["key"] in route_keys or route["path"] in route_paths:
                raise ValueError("ชื่อหรือพาธหน้าโมดูลซ้ำกัน")
            route_keys.add(route["key"])
            route_paths.add(route["path"])
            pages.append(PageSpec(**{key: route[key] for key in keys}))
        module_ids.add(item["id"])
        modules.append(ModuleSpec(**{key: item[key] for key in text_fields},
                                  presentation=PresentationSpec(**presentation), routes=tuple(pages)))
    return tuple(modules)


def navigation_groups() -> tuple[NavigationGroup, ...]:
    """Keep every existing route in exactly one of the four workspace groups."""
    home = PageSpec(
        key="Command center", title="หน้าหลัก", path="app.py", icon="🏠",
        caption="เลือกโมดูล ดูขอบเขตและสถานะการพัฒนา", badge="Hematologic Platform",
    )
    definitions = (
        ("red_cells", "เม็ดเลือดแดงและความผิดปกติของเม็ดเลือดแดง", ":material/hematology:", "rose"),
        ("white_cells", "เม็ดเลือดขาวและความผิดปกติของเม็ดเลือดขาว", ":material/biotech:", "sky"),
        ("other", "อื่นๆ", ":material/apps:", "mint"),
    )
    modules = {module.id: module for module in load_modules()}
    groups = [NavigationGroup("home", home.title, ":material/home:", "lavender", (), (home,))]
    for group_id, title, icon, tone in definitions:
        group_modules = tuple(module for module in modules.values() if module.presentation.group == group_id)
        groups.append(NavigationGroup(
            group_id, title, icon, tone, group_modules,
            tuple(page for module in group_modules for page in module.routes)
            + ((REPORT_DESIGN_PAGE,) if group_id == "other" else ()),
        ))
    return tuple(groups)


def navigation_pages() -> tuple[PageSpec, ...]:
    return tuple(page for group in navigation_groups() for page in group.pages)


def presentation_specs() -> dict[str, PresentationSpec]:
    """Clinical display metadata comes from the catalog; utilities stay separate."""
    return {**{module.id: module.presentation for module in load_modules()}, **UTILITY_PRESENTATION}
