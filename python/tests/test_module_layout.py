from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_rtl_module_has_a_matching_python_module():
    rtl_modules = {path.stem for path in (REPO_ROOT / "src").glob("*.sv")}
    python_modules = {
        path.stem for path in (REPO_ROOT / "python" / "tiny_gpu").glob("*.py")
    }
    assert len(rtl_modules) == 12
    assert rtl_modules <= python_modules
