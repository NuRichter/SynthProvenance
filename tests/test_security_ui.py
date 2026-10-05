import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.utils.paths import safe_arcname, safe_filename, safe_join
from app.utils.system import ToolError, run_tool

ROOT = Path(__file__).resolve().parents[1]


def test_path_safety(tmp_path):
    assert "/" not in safe_filename("../../etc/passwd") and ".." not in safe_filename("..\\..\\boot.ini")
    assert safe_filename("CON.txt").startswith("_")
    with pytest.raises(ValueError):
        safe_join(tmp_path, "..", "escape.txt")
    assert safe_arcname("a/../b", "./c") == "a/b/c"
    with pytest.raises(ValueError):
        safe_arcname("C:evil")


def test_run_tool_requires_argument_list():
    with pytest.raises(ToolError):
        run_tool("echo hello")  # type: ignore[arg-type]


def test_network_guard_blocks_outbound():
    code = ("import socket,sys\nfrom app.utils import netguard\nnetguard.install()\n"
            "try:\n socket.create_connection(('203.0.113.9', 80), timeout=1)\nexcept netguard.NetworkPolicyError:\n sys.exit(0)\n"
            "sys.exit(3)\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr.decode()


def test_png_text_bomb_is_bounded():
    import zlib
    from app.core.containers import make_png_chunk, parse_png, png_text_chunk
    from app.core.synthetic import make_plain_png

    data = make_plain_png()
    bomb = make_png_chunk("zTXt", b"k\x00\x00" + zlib.compress(b"A" * (64 * 1024 * 1024), 9))
    iend = data.rfind(b"IEND") - 4
    data = data[:iend] + bomb + data[iend:]
    st = parse_png(data)
    seg = next(s for s in st.segments if s.name == "zTXt")
    _k, text, note = png_text_chunk(data, seg)
    assert text == "" and "limit" in note


def test_gui_views_render_after_experiment(fx):
    from PySide6.QtWidgets import QApplication
    from app.ui import theme
    from app.ui.controller import AppController
    from app.ui.main_window import NAV, MainWindow
    from app.ui.views.base import REFRESH_ERRORS

    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    ctl = AppController()
    win = MainWindow(ctl, quiet=True)
    win.show()

    def wait():
        t = time.time()
        while ctl.busy or time.time() - t < 0.2:
            app.processEvents()
            time.sleep(0.01)
            assert time.time() - t < 120

    ctl.open_demo_fixture()
    wait()
    ctl.start_experiment()
    wait()
    ctl.run_transformation("c2pa_separation", {})
    wait()
    assert ctl.completed() and ctl.completed()[-1].pixel_metrics["verdict"] == "PIXEL-EXACT"
    for name, _c in NAV:
        win.go(name)
        app.processEvents()
        win.views[name]._do_refresh()
    assert not REFRESH_ERRORS, REFRESH_ERRORS
    assert not win.errors, win.errors
    win.close()
