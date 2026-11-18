import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import app_icon


class IconInputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_accepts_supported_images_and_icon_documents(self):
        for suffix in sorted(app_icon.IMAGE_SUFFIXES):
            path = self.root / ("artwork" + suffix)
            path.write_bytes(b"not-empty")
            self.assertEqual(app_icon.icon_path(str(path)), path.resolve())
        document = self.root / "Brand.icon"
        document.mkdir()
        (document / "icon.json").write_text(json.dumps({"groups": []}))
        self.assertEqual(app_icon.icon_path(str(document)), document.resolve())

    def test_rejects_unsupported_empty_and_oversized_inputs(self):
        text = self.root / "notes.txt"
        text.write_text("not an icon")
        with self.assertRaisesRegex(ValueError, "图标需要"):
            app_icon.icon_path(str(text))
        empty = self.root / "empty.png"
        empty.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "为空"):
            app_icon.icon_path(str(empty))
        huge = self.root / "huge.png"
        with huge.open("wb") as stream:
            stream.truncate(app_icon.MAX_ICON_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "32 MiB"):
            app_icon.icon_path(str(huge))
        missing = self.root / "gone.png"
        with self.assertRaisesRegex(ValueError, "找不到"):
            app_icon.icon_path(str(missing))
        broken = self.root / "Broken.icon"
        broken.mkdir()
        with self.assertRaisesRegex(ValueError, "icon.json"):
            app_icon.icon_path(str(broken))

    def test_rejects_control_characters_and_missing_values(self):
        for value in ("", "   "):
            with self.assertRaisesRegex(ValueError, "请选择图标文件"):
                app_icon.icon_path(value)
        for value in ("a" + chr(0) + ".png", "a" + chr(10) + ".png"):
            with self.assertRaisesRegex(ValueError, "图标路径"):
                app_icon.icon_path(value)

    def test_document_name_comes_from_the_document_and_is_sanitised(self):
        document = self.root / "NCB.icon"
        document.mkdir()
        (document / "icon.json").write_text("{}")
        self.assertEqual(app_icon.icon_document_name(document), "NCB")
        odd = self.root / "my brand.icon"
        odd.mkdir()
        (odd / "icon.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "字母"):
            app_icon.icon_document_name(odd)
        (document / "icon.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "不是对象"):
            app_icon.icon_document_name(document)

    def test_source_facts_fingerprint_images_and_documents(self):
        image = self.root / "artwork.png"
        image.write_bytes(b"one")
        first = app_icon.source_facts(image)
        image.write_bytes(b"two")
        self.assertNotEqual(first, app_icon.source_facts(image))
        document = self.root / "Brand.icon"
        document.mkdir()
        (document / "icon.json").write_text("{}")
        facts = app_icon.source_facts(document)
        self.assertEqual(facts["kind"], "icon")
        self.assertIn("icon.json", facts["files"])
        (document / "icon.json").write_text("{} ")
        self.assertNotEqual(facts["sha256"], app_icon.source_facts(document)["sha256"])

    def test_source_facts_refuse_symbolic_links_in_documents(self):
        document = self.root / "Brand.icon"
        document.mkdir()
        (document / "icon.json").write_text("{}")
        (document / "link.svg").symlink_to("/dev/null")
        with self.assertRaisesRegex(ValueError, "符号链接"):
            app_icon.source_facts(document)


class IconRenderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_image_catalog_points_at_a_1024_square(self):
        image = self.root / "artwork.png"
        image.write_bytes(b"source")
        target = self.root / "catalog/AppIcon.appiconset"
        with patch.object(app_icon, "render_image", return_value={"width": 512, "height": 512}) as render:
            name, rendered = app_icon.appiconset(image, target, fit="fill", padding=5)
        self.assertEqual(name, "AppIcon")
        self.assertEqual(rendered, {"width": 512, "height": 512})
        render.assert_called_once()
        self.assertEqual(render.call_args.args[1], target / "icon-1024.png")
        manifest = json.loads((target / "Contents.json").read_text())
        self.assertEqual(manifest["images"], [{
            "filename": "icon-1024.png", "idiom": "universal",
            "platform": "ios", "size": "1024x1024",
        }])
        self.assertTrue((target.parent / "Contents.json").is_file())

    def test_icon_document_uses_its_own_name_and_no_raster_entry(self):
        document = self.root / "Brand.icon"
        document.mkdir()
        (document / "icon.json").write_text("{}")
        target = self.root / "catalog/AppIcon.appiconset"
        with patch.object(app_icon, "render_image") as render:
            name, rendered = app_icon.appiconset(document, target)
        self.assertEqual(name, "Brand")
        self.assertIsNone(rendered)
        render.assert_not_called()
        manifest = json.loads((target / "Contents.json").read_text())
        self.assertEqual(manifest["images"], [])

    def test_render_options_are_validated_before_running_the_helper(self):
        image = self.root / "artwork.png"
        image.write_bytes(b"source")
        with self.assertRaisesRegex(ValueError, "缩放"):
            app_icon.render_image(image, self.root / "out.png", fit="stretch")
        with self.assertRaisesRegex(ValueError, "背景"):
            app_icon.render_image(image, self.root / "out.png", background="red")
        with self.assertRaisesRegex(ValueError, "留白"):
            app_icon.render_image(image, self.root / "out.png", padding=31)


class IconCompileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_icns_members_skip_non_png_payloads(self):
        png = b"\x89PNG\r\n\x1a\n" + b"payload"
        members = b"ARGB" + b"\x00\x00\x00\x08"
        body = (b"ic07" + (8 + len(png)).to_bytes(4, "big") + png +
                b"ic04" + (8 + len(members)).to_bytes(4, "big") + members)
        icns = self.root / "icon.icns"
        icns.write_bytes(b"icns" + (8 + len(body)).to_bytes(4, "big") + body)
        self.assertEqual(app_icon.icns_members(icns), [png])
        icns.write_bytes(b"nope")
        self.assertEqual(app_icon.icns_members(icns), [])

    def test_compile_requires_the_partial_plist_and_each_asset(self):
        image = self.root / "artwork.png"
        image.write_bytes(b"source")
        output = self.root / "compiled"
        output.mkdir()
        (output / "Assets.xcassets").mkdir()
        with patch.object(app_icon.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            run.return_value.stderr = "actool failed"
            with self.assertRaisesRegex(ValueError, "图标编译失败"):
                app_icon.compile_icon(image, output, "AppIcon")
        with patch.object(app_icon.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = ""
            run.return_value.stderr = ""
            with self.assertRaisesRegex(ValueError, "Info.plist"):
                app_icon.compile_icon(image, output, "AppIcon")


if __name__ == "__main__":
    unittest.main()
