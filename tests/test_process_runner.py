from core.process_runner import ProcessRunner


def test_xray_environment_uses_bundled_geo_assets(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    xray_dir = bin_dir / "xray"
    xray_dir.mkdir(parents=True)
    executable = xray_dir / "xray"
    executable.write_text("", encoding="utf-8")
    (bin_dir / "geoip.dat").write_text("geoip", encoding="utf-8")
    (bin_dir / "geosite.dat").write_text("geosite", encoding="utf-8")
    monkeypatch.delenv("XRAY_LOCATION_ASSET", raising=False)

    env = ProcessRunner._build_environment([str(executable), "run", "-c", "config.json"])

    assert env["XRAY_LOCATION_ASSET"] == str(bin_dir)


def test_non_xray_core_does_not_override_xray_asset_path(monkeypatch):
    monkeypatch.delenv("XRAY_LOCATION_ASSET", raising=False)

    env = ProcessRunner._build_environment(["/usr/bin/sing-box", "run"])

    assert "XRAY_LOCATION_ASSET" not in env
