# settings/project_state.py
# Shared project-level settings that are not tied to one instrument slot.

DEFAULT_PROJECT_SETTINGS = {
    "project_name": "Untitled Project",
    "global_tempo_bpm": 120,
    "global_loop": False,
}

PROJECT_SETTINGS = dict(DEFAULT_PROJECT_SETTINGS)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def ensure_project_settings():
    name = str(PROJECT_SETTINGS.get("project_name") or DEFAULT_PROJECT_SETTINGS["project_name"])

    try:
        bpm = int(round(float(PROJECT_SETTINGS.get("global_tempo_bpm", DEFAULT_PROJECT_SETTINGS["global_tempo_bpm"]))))
    except (TypeError, ValueError):
        bpm = int(DEFAULT_PROJECT_SETTINGS["global_tempo_bpm"])
    bpm = max(40, min(200, bpm))

    loop = _as_bool(PROJECT_SETTINGS.get("global_loop", DEFAULT_PROJECT_SETTINGS["global_loop"]))

    PROJECT_SETTINGS.clear()
    PROJECT_SETTINGS.update({
        "project_name": name,
        "global_tempo_bpm": bpm,
        "global_loop": loop,
    })
    return PROJECT_SETTINGS


def reset_project_settings():
    PROJECT_SETTINGS.clear()
    PROJECT_SETTINGS.update(DEFAULT_PROJECT_SETTINGS)
    return ensure_project_settings()
