import threading
import weakref

from src.core.automation_engine import AutomationThread
from src.core.preset_manager import PresetManager


class FakeSerial:
    def __init__(self):
        self.is_open = True
        self.writes = []

    def write(self, payload):
        self.writes.append(payload.decode("utf-8"))

    def flush(self):
        pass


class FakeParent:
    auto_calibration_enabled = False

    def __init__(self, serial_port):
        self.serial_port = serial_port
        self.steps_seen = []
        self.logs = []

    def generate_command(self, step):
        self.steps_seen.append(step)
        return "XEFV5J90.000\r\n"

    def log(self, message):
        self.logs.append(message)


def test_automation_starts_pump_before_first_step_and_stops_on_finish():
    serial_port = FakeSerial()
    parent = FakeParent(serial_port)
    thread = AutomationThread(
        parent_ref=weakref.ref(parent),
        steps=[{
            "name": "sample",
            "X": {"enable": "E", "direction": "F", "speed": "5", "angle": "90"},
            "pump": {"enable": False, "speed": 10},
            "interval": 0,
        }],
        loop_count=1,
        serial_port=serial_port,
        serial_lock=threading.Lock(),
        injection_pump_speed=55,
    )

    thread.run()

    assert serial_port.writes[0] == "PUMP:SET:55\r\n"
    assert serial_port.writes.index("PUMP:SET:55\r\n") < serial_port.writes.index(
        "XEFV5J90.000\r\n"
    )
    assert "PUMP:OFF\r\n" in serial_port.writes
    assert "pump" not in parent.steps_seen[0]


def test_auto_preset_persists_task_level_injection_pump_speed(tmp_path):
    manager = PresetManager(str(tmp_path / "presets.json"))

    assert manager.save_auto_preset(
        "linked",
        [{"name": "sample"}],
        2,
        injection_pump_speed=60,
    )

    assert manager.load_auto_preset("linked") == {
        "steps": [{"name": "sample"}],
        "loop_count": 2,
        "injection_pump_speed": 60,
    }
