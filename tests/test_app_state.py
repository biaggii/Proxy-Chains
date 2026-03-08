from pathlib import Path

from models.app_state import AppState


def test_app_state_round_trips_auto_start_core(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = AppState(str(state_path))
    state.run_on_startup = True
    state.minimize_on_start = True
    state.auto_start_core = True
    state.save_to_file()

    loaded = AppState(str(state_path))
    loaded.load_from_file()

    assert loaded.run_on_startup is True
    assert loaded.minimize_on_start is True
    assert loaded.auto_start_core is True
