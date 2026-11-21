"""Shared DOM-driven implementation of FormAdapter for Playwright pages."""

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.apply.fields import FormField, ReadBack
from app.core.config import settings

log = logging.getLogger(__name__)

READ_JS = """
(rootSel) => {
  const root = document.querySelector(rootSel) || document.body;
  const vis = (el) => {
    if (!el) return false;
    const st = getComputedStyle(el), r = el.getBoundingClientRect();
    return st.display !== 'none' && st.visibility !== 'hidden' && (r.width > 0 || r.height > 0);
  };
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const labelOf = (el) => {
    if (el.id) {
      const l = document.querySelector('label[for="' + el.id.replace(/"/g, '\\\\"') + '"]');
      if (l) return clean(l.innerText || l.textContent);
    }
    const wrap = el.closest('label');
    if (wrap) return clean(wrap.innerText || wrap.textContent);
    const lb = el.getAttribute('aria-labelledby');
    if (lb) {
      const t = lb.split(' ').map(i => document.getElementById(i)).filter(Boolean)
        .map(n => clean(n.innerText || n.textContent)).join(' ');
      if (t) return t;
    }
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    const fs = el.closest('fieldset');
    if (fs && fs.querySelector('legend')) return clean(fs.querySelector('legend').innerText);
    const prev = el.closest('div,li,p');
    if (prev) {
      const l = prev.querySelector('label');
      if (l) return clean(l.innerText || l.textContent);
    }
    return clean(el.getAttribute('placeholder') || el.name || el.id);
  };
  const out = [], groups = {};
  let n = 0;
  root.querySelectorAll('input,select,textarea').forEach((el) => {
    const type = (el.getAttribute('type') || (el.tagName === 'TEXTAREA' ? 'textarea' : el.tagName === 'SELECT' ? 'select' : 'text')).toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) return;
    const choice = type === 'radio' || type === 'checkbox';
    if (type !== 'file' && !(vis(el) || (choice && vis(el.parentElement)))) return;
    const key = el.id || el.name || ('jc' + (n++));
    const required = el.required || el.getAttribute('aria-required') === 'true';
    if (type === 'radio') {
      const g = el.name || key;
      if (!groups[g]) {
        groups[g] = { key: g, selector: '[name="' + g + '"]', kind: 'radio',
          label: labelOf(el.closest('fieldset') ? el : el), required, options: [], option_values: {} };
        const fs = el.closest('fieldset');
        if (fs && fs.querySelector('legend')) groups[g].label = clean(fs.querySelector('legend').innerText);
        out.push(groups[g]);
      }
      const wrap = el.closest('label');
      const ol = clean(wrap ? (wrap.innerText || wrap.textContent) : (document.querySelector('label[for="' + el.id + '"]') || {}).innerText || el.value);
      groups[g].options.push(ol);
      groups[g].option_values[ol] = el.value;
      groups[g].required = groups[g].required || required;
      return;
    }
    el.setAttribute('data-jc', key);
    const selector = el.id ? '[id="' + el.id + '"]' : el.name ? '[name="' + el.name + '"]' : '[data-jc="' + key + '"]';
    const f = { key, selector, kind: type === 'text' ? 'text' : type, label: labelOf(el), required,
      options: [], option_values: {} };
    if (el.tagName === 'SELECT') {
      f.kind = 'select';
      [...el.options].forEach((o) => {
        const t = clean(o.textContent);
        if (!t || o.disabled || /^(select|choose|please select|--)/i.test(t) && !o.value) return;
        f.options.push(t); f.option_values[t] = o.value;
      });
    }
    if (/\\*\\s*$/.test(f.label)) f.required = true;
    f.label = f.label.replace(/\\s*\\*\\s*$/, '').replace(/\\s*\\(required\\)\\s*$/i, '');
    out.push(f);
  });
  return out;
}
"""

READ_BACK_JS = """
(el) => {
  const files = el.files ? [...el.files].map(f => [f.name, f.size]) : [];
  return { value: el.value || '', checked: !!el.checked, files };
}
"""

YES = {"yes", "y", "true", "1"}


class DomAdapter:
    """Subclasses set the class attributes and override matches/prepare/confirmed."""

    name = "dom"
    uses_fallback = False
    form_selector = "form"
    submit_selector = "button[type=submit], input[type=submit]"
    confirm_text: tuple[str, ...] = ("thank you for applying", "application submitted")
    confirm_url: tuple[str, ...] = ()

    # -- recognition -----------------------------------------------------------
    def matches(self, url: str, page: Any) -> bool:  # pragma: no cover - overridden
        return False

    def prepare(self, page: Any) -> None:
        try:
            page.wait_for_selector(
                self.form_selector, timeout=settings.apply_nav_timeout_ms // 2
            )
        except Exception:  # noqa: BLE001 - no form: read_fields reports a layout change
            log.info("adapter %s: form not found", self.name)

    # -- fields ----------------------------------------------------------------
    def read_fields(self, page: Any) -> list[FormField]:
        raw = page.evaluate(READ_JS, self.form_selector)
        return [FormField(**r) for r in raw]

    def fill(
        self,
        page: Any,
        values: dict[str, str | Path],
        fields: list[FormField],
        pace: Callable[[], None],
    ) -> None:
        for f in fields:
            if f.key not in values:
                continue
            value = values[f.key]
            loc = page.locator(f.selector)
            if f.kind == "file":
                loc.first.set_input_files(str(value))
            elif f.kind == "select":
                v = f.option_values.get(str(value), str(value))
                loc.first.select_option(value=v)
            elif f.kind == "radio":
                v = f.option_values.get(str(value), str(value))
                page.locator(f'{f.selector}[value="{v}"]').first.check()
            elif f.kind == "checkbox":
                if str(value).strip().lower() in YES:
                    loc.first.check()
            else:
                loc.first.fill(str(value))
            pace()

    def read_back(self, page: Any, fields: list[FormField]) -> dict[str, ReadBack]:
        out: dict[str, ReadBack] = {}
        for f in fields:
            try:
                if f.kind == "radio":
                    checked = page.locator(f"{f.selector}:checked")
                    rb = ReadBack(
                        value=checked.first.input_value() if checked.count() else "",
                        checked=bool(checked.count()),
                    )
                else:
                    r = page.locator(f.selector).first.evaluate(READ_BACK_JS)
                    rb = ReadBack(
                        r["value"], r["checked"], [tuple(x) for x in r["files"]]
                    )
                    if f.kind == "file":
                        rb.value = ""
                out[f.key] = rb
            except Exception:  # noqa: BLE001 - unreadable means unverified, which blocks
                out[f.key] = ReadBack()
        return out

    # -- submit ----------------------------------------------------------------
    def submit(self, page: Any) -> None:
        page.locator(self.submit_selector).first.click()

    def confirmed(self, page: Any) -> bool:
        try:
            text = page.inner_text("body").lower()
        except Exception:  # noqa: BLE001
            text = ""
        url = page.url.lower()
        return any(t in text for t in self.confirm_text) or any(
            u in url for u in self.confirm_url
        )


def label_has(label: str, pattern: str) -> bool:
    return re.search(pattern, label, re.IGNORECASE) is not None
