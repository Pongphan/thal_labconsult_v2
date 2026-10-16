"""Light pastel and softened dark tokens for each hematology topic.

Cards use application-owned st-key classes. Historical gradient endpoints remain
available to the archived contrast-audit scripts; current cards use solid fills.
"""
from __future__ import annotations

from dataclasses import dataclass
from utils.module_registry import presentation_specs


@dataclass(frozen=True)
class CardTone:
    name: str
    light: str
    dark: str
    accent: str
    dark_accent: str
    border: str
    dark_border: str
    light_end: str
    dark_end: str


CARD_TONES = {
    "rose": CardTone("ชมพูกุหลาบ", "#FBE7EE", "#55314A", "#943E5C", "#F4ACCF", "#A46C82", "#BC6E99", "#FFF8F7", "#342735"),
    "lavender": CardTone("ลาเวนเดอร์", "#ECE8FA", "#433769", "#63508F", "#D1BEFA", "#8B7AAC", "#9B87D8", "#F8F5FE", "#2D2942"),
    "sky": CardTone("สีฟ้า", "#E5F1F8", "#294C64", "#396B84", "#98DEFA", "#63879D", "#5EA1C0", "#F4FAFF", "#243444"),
    "lilac": CardTone("ม่วงไลแลค", "#F3E6F6", "#533462", "#805389", "#ECB9FA", "#9A72A4", "#B87EC9", "#FCF7FB", "#372A43"),
    "peach": CardTone("พีช", "#FBEADB", "#544032", "#86592D", "#F4CCA4", "#9B7A56", "#B8926E", "#FFF9F1", "#3C3029"),
    "butter": CardTone("สีเหลือง", "#F6EED4", "#4A4631", "#75601F", "#F4E5A5", "#958544", "#B4A56F", "#FFFCEE", "#353329"),
    "coral": CardTone("คอรัล", "#FBE6E2", "#563939", "#984D42", "#F4BBB1", "#A66F61", "#BC8882", "#FFF6F2", "#3C2C30"),
    "mint": CardTone("เขียวมินต์", "#E4F1EA", "#294C48", "#376952", "#97E4CC", "#628570", "#5DA497", "#F5FCF7", "#253733"),
    "teal": CardTone("เขียวน้ำทะเล", "#DDF3F3", "#2D4D50", "#285F65", "#ADE1E3", "#648C90", "#77A7AA", "#F1FBFB", "#293B40"),
    "indigo": CardTone("คราม", "#E7EBFA", "#3D4565", "#465A91", "#C5D0F4", "#7C8BB4", "#8F9FC9", "#F5F7FE", "#30364C"),
}

# Opaque text and boundary tokens avoid compounded native caption opacity.
# The contrast audit samples the full sRGB gradients, not only their endpoints.
TEXT_TOKENS = {
    "light": {"ink": "#120D18", "muted": "#504157", "stroke": "#88718D", "focus": "#803050"},
    "dark": {"ink": "#F6F8FF", "muted": "#D8E2F5", "stroke": "#9EACC5", "focus": "#A7DFF4"},
}

# Opaque stops make contrast predictable at every point along each gradient.
SURFACE_STOPS = {
    "light": {
        "canvas": ("#FFF7F9", "#F6F2FA", "#F2F7F5"),
        "surface": ("#FFFDFE", "#F6F0F7"),
        "primary": ("#9D4566", "#704575"),
        "toolbar": ("#FFF9FB", "#F6F0F8"),
    },
    "dark": {
        "canvas": ("#18131F", "#211A2B", "#1B2528"),
        "surface": ("#281F32", "#241F2F"),
        "primary": ("#913D60", "#644169"),
        "toolbar": ("#2E2235", "#251F30"),
    },
}

MODULE_TONES = {key: item.tone for key, item in presentation_specs().items()}


def resolve_tone(tone: str) -> str:
    resolved = MODULE_TONES.get(tone, tone)
    if resolved not in CARD_TONES:
        raise ValueError(f"Unknown card tone: {tone}")
    return resolved


def card_styles(dark: bool) -> str:
    """Render the shared learning-lab shell without restyling native alerts."""
    from ui.shell_styles import shell_styles
    return shell_styles(dark, CARD_TONES, TEXT_TOKENS)
