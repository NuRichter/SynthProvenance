import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_build_bat_is_ascii_crlf_with_all_stages():
    raw = (ROOT / "build.bat").read_bytes()
    assert all(b < 128 for b in raw), "build.bat must be ASCII"
    assert raw.count(b"\n") == raw.count(b"\r\n"), "build.bat must use CRLF"
    text = raw.decode("ascii")
    for n in (1, 2):
        assert f"[{n}/8]" in text
    assert "BUILD SUCCESSFUL" in text and "BUILD FAILED" in text and "pause" in text
    assert "dist\\SynthProvenance\\SynthProvenance.exe" in text
    stages = (ROOT / "scripts" / "build.py").read_text()
    for name in ("Installing dependencies", "Validating source", "Running tests", "Building executable",
                 "Verifying executable", "Preparing distribution"):
        assert name in stages


def test_powershell_scripts_ascii_crlf():
    for rel in ("build.ps1", "scripts/bootstrap.ps1"):
        raw = (ROOT / rel).read_bytes()
        assert all(b < 128 for b in raw), rel
        assert raw.count(b"\n") == raw.count(b"\r\n"), rel
    boot = (ROOT / "scripts" / "bootstrap.ps1").read_text()
    assert "Get-AuthenticodeSignature" in boot and "Read-Host" in boot  # consent + signature check before any download


def test_requirements_are_exactly_pinned():
    for rel in ("requirements.txt", "requirements-build.txt"):
        for line in (ROOT / rel).read_text().splitlines():
            line = line.split("#")[0].strip()
            if line:
                assert re.match(r"^[A-Za-z0-9_.\-]+==[0-9][^ ;]*( ;.*)?$", line), line


def test_spec_and_resources_present():
    spec = (ROOT / "SynthProvenance.spec").read_text()
    assert "console=False" in spec and "icon.ico" in spec and "platforms" in spec
    assert '"data"' in spec  # the taxonomy/library data folder is bundled
    assert "app/i18n/locales" in spec  # the 30-language locale files are bundled
    for rel in ("assets/icon.ico", "assets/icon.png", "assets/version_info.txt", "assets/templates/report.html",
                "config/default_config.json", "config/synthid_sources.json", "LICENSE", "README.md", "tools/README.md",
                "data/fingerprint_taxonomy.json", "data/research_library.json", "data/research_catalog.json",
                "data/source/AI_Generative_Image_Fingerprints_Taxonomy_APA.txt", "CITATION.cff", "SECURITY.md",
                "CODE_OF_CONDUCT.md", "licenses/THIRD_PARTY_NOTICES.md", "app/i18n/locales/en.json",
                "app/i18n/locales/id.json", "app/i18n/locales/ar.json", "app/i18n/locales/zh.json"):
        assert (ROOT / rel).is_file(), rel
    for rel in ("ARCHITECTURE", "RESEARCH_METHOD", "EXPERIMENT_PROTOCOL", "LOCAL_PROCESSING", "FORMAT_HANDLING",
                "SYNTHID_RESEARCH_LAB", "SYNTHID_RESEARCH_SOURCES", "SYNTHID_IMPLEMENTATION_SURVEY",
                "FINGERPRINT_TAXONOMY", "SOFTWARE_QUALITY", "IMPLEMENTATION_GAP_ANALYSIS", "RESEARCH_SCOPE",
                "RESEARCH_PROTOCOL", "METHOD_VALIDATION"):
        assert (ROOT / "docs" / f"{rel}.md").is_file(), rel
