"""Descriptions and editable state survive old and new Streamlit signatures."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from ui import streamlit_compat as compat


class StreamlitCompatibilityTests(unittest.TestCase):
    def test_older_display_commands_keep_visible_description_and_result(self):
        for name in ("dataframe", "plotly_chart"):
            with self.subTest(command=name):
                data, returned = object(), object()
                events = []

                def older_renderer(value, *, width, key):
                    events.append(("render", value, width, key))
                    return returned

                with patch.object(compat.st, name, older_renderer), patch.object(
                    compat.st, "caption", side_effect=lambda text: events.append(("description", text))
                ):
                    actual = getattr(compat, name)(data, width="stretch", key="result", alt="ผลที่ใช้ทบทวน")
                self.assertIs(actual, returned)
                self.assertEqual(events, [("description", "ผลที่ใช้ทบทวน"), ("render", data, "stretch", "result")])

    def test_new_commands_receive_native_alt_without_duplicate_caption(self):
        for name in ("dataframe", "data_editor", "plotly_chart", "iframe"):
            for description in ("ข้อมูลจากการประเมินครั้งล่าสุด", "", None):
                with self.subTest(command=name, alt=description):
                    received = []
                    data, returned = object(), object()

                    def newer_renderer(value, *, alt="native default", width="stretch"):
                        received.append((value, alt, width))
                        return returned

                    with patch.object(compat.st, name, newer_renderer), patch.object(compat.st, "caption") as caption:
                        actual = getattr(compat, name)(data, alt=description, width=640)
                    self.assertIs(actual, returned)
                    self.assertEqual(received, [(data, "native default" if description is None else description, 640)])
                    caption.assert_not_called()

    def test_older_iframe_preserves_html_size_keyboard_focus_and_return(self):
        html, returned = "<!doctype html><html><body>รายงาน DRAFT</body></html>", object()
        received = []

        def older_iframe(src, *, height, width, tab_index):
            received.append((src, height, width, tab_index))
            return returned

        with patch.object(compat.st, "iframe", older_iframe), patch.object(compat.st, "caption") as caption:
            actual = compat.iframe(html, height=850, width="stretch", tab_index=0, alt="รายงานสมมติ")
        self.assertIs(actual, returned)
        self.assertEqual(received, [(html, 850, "stretch", 0)])
        caption.assert_called_once_with("รายงานสมมติ")

    def test_editor_preserves_widget_identity_callback_arguments_and_edited_return(self):
        original, edited, column_config = object(), object(), {"result": object()}
        callback_args, callback_kwargs = (object(),), {"source": object()}
        invoked = []
        received = {}

        def on_change(*args, **kwargs):
            invoked.append((args, kwargs))

        def older_editor(data, *, key, on_change, args, kwargs, column_config, num_rows, disabled):
            received.update(data=data, key=key, on_change=on_change, args=args, kwargs=kwargs,
                            column_config=column_config, num_rows=num_rows, disabled=disabled)
            return edited

        with patch.object(compat.st, "data_editor", older_editor), patch.object(compat.st, "caption") as caption:
            actual = compat.data_editor(
                original, key="pcr_calls", on_change=on_change, args=callback_args, kwargs=callback_kwargs,
                column_config=column_config, num_rows="dynamic", disabled=["target"], alt="ผล PCR ที่แก้ไขได้",
            )
        self.assertIs(actual, edited)
        self.assertIs(received["data"], original)
        self.assertEqual(received["key"], "pcr_calls")
        self.assertIs(received["on_change"], on_change)
        self.assertIs(received["args"], callback_args)
        self.assertIs(received["kwargs"], callback_kwargs)
        self.assertIs(received["column_config"], column_config)
        self.assertEqual((received["num_rows"], received["disabled"]), ("dynamic", ["target"]))
        self.assertFalse(invoked)
        caption.assert_called_once_with("ผล PCR ที่แก้ไขได้")

    def test_unrelated_unsupported_keywords_are_not_silently_filtered(self):
        def strict_renderer(data, *, key=None):
            return data

        for name in ("dataframe", "data_editor", "plotly_chart", "iframe"):
            with self.subTest(command=name), patch.object(compat.st, name, strict_renderer), patch.object(compat.st, "caption"):
                with self.assertRaisesRegex(TypeError, "unsupported_option"):
                    getattr(compat, name)(object(), alt="คำอธิบาย", unsupported_option=True)


if __name__ == "__main__":
    unittest.main()
