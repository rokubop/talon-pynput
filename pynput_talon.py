import time
from typing import Any, Union
from talon import Module

try:
    from pynput import keyboard, mouse
except ImportError:
    keyboard = None
    mouse = None
    print("ERROR: talon-pynput requires pynput. See installation instructions:")
    print("       https://github.com/rokubop/talon-pynput#install-pynput")

mod = Module()

_kb_listener = None
_mouse_listener = None
_key_registry = {}       # normalized_key -> [(on_press, on_release), ...]
_combo_registry = {}     # frozenset -> [{"on_press", "on_release", "fired"}, ...]
_sequence_registry = {}  # key_str -> [{"steps", "current_step", "last_step_time", "on_press"}, ...]
_hold_state = {}

SEQUENCE_TIMEOUT = 0.3

KEY_ALIASES = {
    "super": "cmd",
    "win": "cmd",
    "windows": "cmd",
    "control": "ctrl",
    "escape": "esc",
    "return": "enter",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "cmd_l": "cmd",
    "cmd_r": "cmd",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
}

MOUSE_BUTTON_NAMES = {"mouse_left", "mouse_right", "mouse_middle"}


def _normalize(name: str) -> str:
    name = name.strip().lower()
    return KEY_ALIASES.get(name, name)


def _key_from_pynput(key) -> str | None:
    if hasattr(key, "char") and key.char is not None:
        return key.char.lower()
    elif hasattr(key, "name"):
        return _normalize(key.name)
    return None


def _button_to_str(button) -> str | None:
    if mouse is None:
        return None
    mapping = {
        mouse.Button.left: "mouse_left",
        mouse.Button.right: "mouse_right",
        mouse.Button.middle: "mouse_middle",
    }
    return mapping.get(button)


def _parse(key_str: str):
    """Returns (key, None) for single key, or (None, frozenset) for combo."""
    key_str = key_str.replace("+", "-")
    parts = [_normalize(p) for p in key_str.split("-")]
    if len(parts) == 1:
        return parts[0], None
    return None, frozenset(parts)


def _parse_full(key_str: str):
    """Parse a full key string into (single, combo, sequence).
    Only one will be non-None.
    """
    steps = key_str.strip().split()
    if len(steps) == 1:
        single, combo = _parse(steps[0])
        return single, combo, None

    parsed_steps = []
    for step in steps:
        single, combo = _parse(step)
        parsed_steps.append(combo if combo else single)
    return None, None, parsed_steps


def _is_mouse_key(name: str) -> bool:
    return name in MOUSE_BUTTON_NAMES


def _step_has_mouse(step) -> bool:
    if isinstance(step, frozenset):
        return any(_is_mouse_key(k) for k in step)
    return _is_mouse_key(step)


def _step_has_kb(step) -> bool:
    if isinstance(step, frozenset):
        return any(not _is_mouse_key(k) for k in step)
    return not _is_mouse_key(step)


def _any_mouse_registered() -> bool:
    for key in _key_registry:
        if _is_mouse_key(key) and _key_registry[key]:
            return True
    for combo_keys in _combo_registry:
        if _combo_registry[combo_keys] and any(_is_mouse_key(k) for k in combo_keys):
            return True
    for key_str, stack in _sequence_registry.items():
        if stack:
            for seq in stack:
                if any(_step_has_mouse(step) for step in seq["steps"]):
                    return True
    return False


def _any_kb_registered() -> bool:
    for key in _key_registry:
        if not _is_mouse_key(key) and _key_registry[key]:
            return True
    for combo_keys in _combo_registry:
        if _combo_registry[combo_keys] and any(not _is_mouse_key(k) for k in combo_keys):
            return True
    for key_str, stack in _sequence_registry.items():
        if stack:
            for seq in stack:
                if any(_step_has_kb(step) for step in seq["steps"]):
                    return True
    return False


def _check_sequences(key_str: str):
    now = time.monotonic()
    for key, stack in _sequence_registry.items():
        if not stack:
            continue
        seq = stack[-1]
        step_idx = seq["current_step"]

        if step_idx > 0 and (now - seq["last_step_time"]) > SEQUENCE_TIMEOUT:
            seq["current_step"] = 0
            step_idx = 0

        expected = seq["steps"][step_idx]

        if isinstance(expected, frozenset):
            matched = key_str in expected and all(
                _hold_state.get(k, False) for k in expected
            )
        else:
            matched = key_str == expected

        if matched:
            if step_idx == len(seq["steps"]) - 1:
                seq["current_step"] = 0
                seq["last_step_time"] = 0
                if seq["on_press"]:
                    seq["on_press"]()
            else:
                seq["current_step"] = step_idx + 1
                seq["last_step_time"] = now


def _fire_press(key_str: str):
    was_held = _hold_state.get(key_str, False)
    _hold_state[key_str] = True

    if was_held:
        return

    if key_str in _key_registry and _key_registry[key_str]:
        on_press, _ = _key_registry[key_str][-1]
        if on_press:
            on_press()

    for combo_keys, stack in _combo_registry.items():
        if not stack:
            continue
        data = stack[-1]
        if key_str in combo_keys and not data["fired"]:
            if all(_hold_state.get(k, False) for k in combo_keys):
                data["fired"] = True
                if data["on_press"]:
                    data["on_press"]()

    if _sequence_registry:
        _check_sequences(key_str)


def _fire_release(key_str: str):
    for combo_keys, stack in _combo_registry.items():
        if not stack:
            continue
        data = stack[-1]
        if key_str in combo_keys and data["fired"]:
            data["fired"] = False
            if data["on_release"]:
                data["on_release"]()

    _hold_state[key_str] = False

    if key_str in _key_registry and _key_registry[key_str]:
        _, on_release = _key_registry[key_str][-1]
        if on_release:
            on_release()


def _on_kb_press(key):
    key_str = _key_from_pynput(key)
    if key_str is not None:
        _fire_press(key_str)


def _on_kb_release(key):
    key_str = _key_from_pynput(key)
    if key_str is not None:
        _fire_release(key_str)


def _on_mouse_click(x, y, button, pressed):
    key_str = _button_to_str(button)
    if key_str is None:
        return
    if pressed:
        _fire_press(key_str)
    else:
        _fire_release(key_str)


def _start_kb():
    global _kb_listener
    if _kb_listener is None and keyboard is not None:
        _kb_listener = keyboard.Listener(
            on_press=_on_kb_press,
            on_release=_on_kb_release,
            daemon=True,
        )
        print("Starting pynput keyboard listener (Talon thread warning expected)")
        _kb_listener.start()


def _start_mouse():
    global _mouse_listener
    if _mouse_listener is None and mouse is not None:
        _mouse_listener = mouse.Listener(
            on_click=_on_mouse_click,
            daemon=True,
        )
        print("Starting pynput mouse listener (Talon thread warning expected)")
        _mouse_listener.start()


def _stop_if_empty():
    global _kb_listener, _mouse_listener

    if not _any_kb_registered() and _kb_listener is not None:
        _kb_listener.stop()
        _kb_listener = None
        _hold_state.clear()
        print("Stopped pynput keyboard listener")

    if not _any_mouse_registered() and _mouse_listener is not None:
        _mouse_listener.stop()
        _mouse_listener = None
        print("Stopped pynput mouse listener")


def _cleanup_empty():
    """Remove empty stacks from registries."""
    for key in list(_key_registry):
        if not _key_registry[key]:
            del _key_registry[key]
    for key in list(_combo_registry):
        if not _combo_registry[key]:
            del _combo_registry[key]
    for key in list(_sequence_registry):
        if not _sequence_registry[key]:
            del _sequence_registry[key]


def _do_register(key_str: str, on_press=None, on_release=None):
    single, combo, sequence = _parse_full(key_str)

    if sequence:
        _sequence_registry.setdefault(key_str, []).append({
            "steps": sequence,
            "current_step": 0,
            "last_step_time": 0,
            "on_press": on_press,
        })
    elif combo:
        _combo_registry.setdefault(combo, []).append({
            "on_press": on_press,
            "on_release": on_release,
            "fired": False,
        })
    else:
        _key_registry.setdefault(single, []).append((on_press, on_release))

    if sequence:
        needs_kb = any(_step_has_kb(s) for s in sequence)
        needs_mouse = any(_step_has_mouse(s) for s in sequence)
    elif combo:
        needs_kb = any(not _is_mouse_key(k) for k in combo)
        needs_mouse = any(_is_mouse_key(k) for k in combo)
    else:
        needs_kb = not _is_mouse_key(single)
        needs_mouse = _is_mouse_key(single)

    if needs_kb:
        _start_kb()
    if needs_mouse:
        _start_mouse()


def _do_unregister(key_str: str):
    """Remove all registrations for a key."""
    single, combo, sequence = _parse_full(key_str)

    if sequence:
        _sequence_registry.pop(key_str, None)
    elif combo:
        _combo_registry.pop(combo, None)
    else:
        _key_registry.pop(single, None)
    _stop_if_empty()


def _do_unregister_last(key_str: str):
    """Remove the most recent registration for a key, restoring the previous one."""
    single, combo, sequence = _parse_full(key_str)

    if sequence:
        stack = _sequence_registry.get(key_str)
        if stack:
            stack.pop()
    elif combo:
        stack = _combo_registry.get(combo)
        if stack:
            stack.pop()
    else:
        stack = _key_registry.get(single)
        if stack:
            stack.pop()

    _cleanup_empty()
    _stop_if_empty()


@mod.action_class
class Actions:
    def pynput_register(key: Union[str, dict], on_press: callable = None, on_release: callable = None):
        """Register key(s) with the pynput listener. Pushes onto stack if key already registered.

        Single:    pynput_register("f22", press_fn, release_fn)
        Combo:     pynput_register("ctrl-super", press_fn)
        Mouse:     pynput_register("mouse_left", press_fn, release_fn)
        Mixed:     pynput_register("ctrl-mouse_left", press_fn, release_fn)
        Sequence:  pynput_register("j j", press_fn)
        Multiple:  pynput_register({"f22": (press_fn, release_fn), "f23": (press_fn,)})
        """
        if keyboard is None:
            print("ERROR: talon-pynput requires pynput.")
            return
        if isinstance(key, dict):
            for k, cbs in key.items():
                if isinstance(cbs, (list, tuple)):
                    _do_register(
                        k,
                        cbs[0] if len(cbs) > 0 else None,
                        cbs[1] if len(cbs) > 1 else None,
                    )
                else:
                    _do_register(k, cbs)
        else:
            _do_register(key, on_press, on_release)

    def pynput_unregister(key: Union[str, list]):
        """Remove all registrations for key(s).

        Single:   pynput_unregister("f22")
        Multiple: pynput_unregister(["f22", "f23", "f24"])
        """
        if isinstance(key, (list, tuple)):
            for k in key:
                _do_unregister(k)
        else:
            _do_unregister(key)

    def pynput_unregister_last(key: Union[str, list]):
        """Remove the most recent registration for key(s), restoring the previous one.

        Single:   pynput_unregister_last("f22")
        Multiple: pynput_unregister_last(["f22", "f23", "f24"])
        """
        if isinstance(key, (list, tuple)):
            for k in key:
                _do_unregister_last(k)
        else:
            _do_unregister_last(key)

    def pynput_is_held(key: str) -> bool:
        """Check if a key, mouse button, or combo is currently held down."""
        single, combo, _ = _parse_full(key)
        if combo:
            return all(_hold_state.get(k, False) for k in combo)
        if single:
            return _hold_state.get(single, False)
        return False

    def pynput_is_active() -> bool:
        """Check if any pynput listener is running."""
        return _kb_listener is not None or _mouse_listener is not None
