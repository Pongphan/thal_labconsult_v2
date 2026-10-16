"""Escaped, non-interactive brand composition and original decorative vector art."""
from __future__ import annotations

from base64 import b64encode
from html import escape


# Abstract blood-cell artwork, not a microscope image or diagnostic reference.
CELL_ART = """
<svg class="thal-cell-art" viewBox="0 0 440 300" xmlns="http://www.w3.org/2000/svg"
     aria-hidden="true" focusable="false">
  <defs>
    <radialGradient id="thal-rbc" cx="38%" cy="28%" r="75%">
      <stop offset="0" stop-color="#F5B7C7"/>
      <stop offset=".5" stop-color="#D87898"/>
      <stop offset="1" stop-color="#9C4566"/>
    </radialGradient>
    <radialGradient id="thal-rbc-center">
      <stop offset="0" stop-color="#F8D2DC"/>
      <stop offset=".6" stop-color="#E89BB3"/>
      <stop offset="1" stop-color="#AF5579"/>
    </radialGradient>
    <radialGradient id="thal-wbc" cx="35%" cy="28%" r="75%">
      <stop offset="0" stop-color="#FFF7FC"/>
      <stop offset="1" stop-color="#D8BEDF"/>
    </radialGradient>
    <linearGradient id="thal-nucleus" x2="1" y2="1">
      <stop stop-color="#A98BBA"/>
      <stop offset="1" stop-color="#715680"/>
    </linearGradient>
  </defs>
  <g fill="none" stroke="#9C4566" stroke-width="1" opacity=".22">
    <ellipse cx="223" cy="148" rx="178" ry="109" transform="rotate(-15 223 148)"/>
    <ellipse cx="223" cy="148" rx="144" ry="131" transform="rotate(25 223 148)" stroke-dasharray="3 8"/>
    <path d="M55 236 124 196 221 199 323 104 389 74" stroke-dasharray="2 6"/>
  </g>
  <g transform="translate(147 115) rotate(-22)">
    <ellipse cy="7" rx="82" ry="54" fill="#7E395E" opacity=".10"/>
    <ellipse rx="82" ry="53" fill="url(#thal-rbc)"/>
    <ellipse cy="-2" rx="43" ry="26" fill="url(#thal-rbc-center)"/>
    <path d="M-63-15C-42-39 4-45 43-28" fill="none" stroke="#FFE3EB" stroke-width="3" opacity=".55" stroke-linecap="round"/>
  </g>
  <g transform="translate(308 109)">
    <circle cy="5" r="54" fill="#4D355F" opacity=".08"/>
    <circle r="54" fill="url(#thal-wbc)" stroke="#C6A6CF" stroke-width="1.5"/>
    <path d="M-24-7C-40-27-7-41 4-22 20-34 42-13 24 0 42 21 7 35-5 18-25 33-40 9-24-7Z" fill="url(#thal-nucleus)"/>
    <g fill="#B594BE" opacity=".65">
      <circle cx="-30" cy="24" r="2"/><circle cx="31" cy="26" r="2.2"/>
      <circle cx="25" cy="-34" r="1.8"/><circle cx="-35" cy="-16" r="1.8"/>
      <circle cx="-4" cy="39" r="1.5"/><circle cx="37" cy="-4" r="1.5"/>
    </g>
  </g>
  <g transform="translate(241 219) rotate(20)">
    <ellipse cy="5" rx="64" ry="38" fill="#7E395E" opacity=".10"/>
    <ellipse rx="64" ry="38" fill="url(#thal-rbc)"/>
    <ellipse cy="-1" rx="34" ry="18" fill="url(#thal-rbc-center)"/>
    <path d="M-47-14C-21-31 8-29 29-21" fill="none" stroke="#FFE3EB" stroke-width="2.5" opacity=".6" stroke-linecap="round"/>
  </g>
  <g transform="translate(82 213) rotate(-26)" fill="#9CC5B8" stroke="#709E91" stroke-width="1">
    <ellipse rx="12" ry="8"/><ellipse cx="26" cy="11" rx="8" ry="6"/>
  </g>
  <g fill="#D9B878"><circle cx="214" cy="59" r="4"/><circle cx="359" cy="202" r="6"/><circle cx="370" cy="221" r="3"/></g>
  <g fill="#9C4566" opacity=".35"><circle cx="49" cy="151" r="3"/><circle cx="377" cy="61" r="3"/><circle cx="150" cy="265" r="3"/></g>
</svg>
"""
# Streamlit sanitizes HTML with an HTML-only profile. An image keeps the SVG
# intact without scripts, external requests, or unsupported inline SVG tags.
CELL_ART_URL = "data:image/svg+xml;base64," + b64encode(CELL_ART.encode("utf-8")).decode("ascii")


def hero_markup(title: str, subtitle: str, eyebrow: str, *, compact: bool = False) -> str:
    """Keep the hero static and accessible; all actions remain native widgets."""
    brand_class = " thal-hero-brand" if title == "ThalLink" else ""
    return (
        f'<section class="thal-hero{" thal-hero--compact" if compact else ""}" aria-labelledby="thal-hero-title">'
        '<div class="thal-hero-copy">'
        f'<p class="thal-eyebrow"><span aria-hidden="true"></span>{escape(eyebrow)}</p>'
        f'<h1 class="thal-hero-title{brand_class}" id="thal-hero-title">{escape(title)}</h1>'
        f'<p class="thal-hero-description">{escape(subtitle)}</p>'
        '<div class="thal-hero-tags" aria-label="ลำดับการใช้เครื่องมือ">'
        '<span>ผลตรวจ</span><b aria-hidden="true">→</b><span>หลักฐาน</span>'
        '<b aria-hidden="true">→</b><span>การทบทวน</span></div></div>'
        '<div class="thal-hero-visual" aria-hidden="true">'
        f'<img class="thal-cell-art" src="{CELL_ART_URL}" alt="" width="440" height="300"></div>'
        '</section>'
    )
