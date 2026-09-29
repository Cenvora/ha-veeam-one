"""Validation for the shipped automation blueprints.

These need no Home Assistant, and check the things that actually break a blueprint in the
wild and that no YAML linter would catch: an `!input` that was never declared, a declared input
nothing uses (a UI field that does nothing), a `source_url` that does not match where the file
really lives (which breaks the import link), selectors pointing at a different integration,
and a blueprint that tells users to pick an entity the integration does not create.
test_blueprint_behaviour.py runs them in Home Assistant.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).parent.parent
BLUEPRINT_DIR = REPO / "blueprints" / "automation" / "veeam_one"
INTEGRATION = REPO / "custom_components" / "veeam_one"
REPO_SLUG = "Cenvora/ha-veeam-one"


class BlueprintLoader(yaml.SafeLoader):
    """SafeLoader that understands Home Assistant's blueprint tags."""


class Input:
    """Stands in for an !input tag so the document can be walked."""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"!input {self.name}"


BlueprintLoader.add_constructor("!input", lambda loader, node: Input(loader.construct_scalar(node)))


def blueprint_files():
    return sorted(BLUEPRINT_DIR.glob("*.yaml"))


def load(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=BlueprintLoader)


def walk(node):
    """Yield every value in a nested structure."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def used_inputs(document):
    return {node.name for node in walk(document) if isinstance(node, Input)}


def source(name):
    return (INTEGRATION / name).read_text(encoding="utf-8")


def test_blueprints_exist():
    assert blueprint_files(), "no blueprints found — has the directory moved?"


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_has_required_metadata(path):
    """Missing metadata makes a blueprint unimportable or anonymous in the UI."""
    document = load(path)
    meta = document.get("blueprint")

    assert meta, "no blueprint: block"
    assert meta.get("domain") == "automation"
    assert meta.get("name"), "needs a name for the blueprint list"
    assert meta.get("description"), "needs a description explaining which entities to pick"
    assert meta.get("input"), "an automation blueprint with no inputs is just an automation"


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_source_url_matches_the_file_location(path):
    """The import link is built from source_url; a stale one imports the wrong file."""
    document = load(path)
    source_url = document["blueprint"].get("source_url")

    assert source_url, "needs source_url so Home Assistant can offer re-import"
    expected = f"https://github.com/{REPO_SLUG}/blob/main/{path.relative_to(REPO).as_posix()}"
    assert source_url == expected, f"expected {expected}"


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_every_input_is_declared(path):
    """An !input with no declaration fails at import time with a schema error."""
    document = load(path)
    declared = set(document["blueprint"]["input"])

    undeclared = used_inputs(document) - declared
    assert not undeclared, f"used but not declared: {sorted(undeclared)}"


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_every_declared_input_is_used(path):
    """A declared input nothing references is a UI field that silently does nothing."""
    document = load(path)
    declared = set(document["blueprint"]["input"])

    unused = declared - used_inputs(document)
    assert not unused, f"declared but never used: {sorted(unused)}"


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_is_a_runnable_automation(path):
    """Uses the current plural keys, which the supported Home Assistant versions guarantee."""
    document = load(path)

    assert "triggers" in document, "no triggers"
    assert "actions" in document, "no actions"
    assert "trigger" not in document, "singular trigger: is the pre-2024.10 spelling"
    assert "action" not in document, "singular action: is the pre-2024.10 spelling"
    assert "condition" not in document, "singular condition: is the pre-2024.10 spelling"

    for entry in document["triggers"]:
        assert "trigger" in entry, f"trigger entry missing its platform: {entry}"
        assert "platform" not in entry, "platform: is the pre-2024.10 spelling"


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_entity_selectors_target_this_integration(path):
    """A selector without the filter lists every entity in the user's system."""
    document = load(path)

    for name, spec in document["blueprint"]["input"].items():
        selector = spec.get("selector", {})
        if "entity" not in selector:
            continue
        filters = (selector["entity"] or {}).get("filter")
        assert filters, f"{name}: entity selector should filter to this integration"
        integrations = {f.get("integration") for f in filters}
        assert integrations == {"veeam_one"}, f"{name}: filters {integrations}"


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_device_class_filters_exist_in_the_integration(path):
    """Filtering on a device class the integration never sets leaves an empty picker."""
    document = load(path)
    platform_source = {"sensor": source("sensor.py"), "binary_sensor": source("binary_sensor.py")}

    for name, spec in document["blueprint"]["input"].items():
        selector = spec.get("selector", {})
        for entry in (selector.get("entity") or {}).get("filter", []):
            device_class = entry.get("device_class")
            if not device_class:
                continue
            text = platform_source[entry["domain"]]
            prefix = "Binary" if entry["domain"] == "binary_sensor" else ""
            assert f"{prefix}SensorDeviceClass.{device_class.upper()}" in text, (
                f"{name}: no {entry['domain']} has device class {device_class}"
            )


def entity_names():
    """Every entity name the integration's translations define, as a pattern."""
    strings = json.loads(source("strings.json"))
    names = {}
    for platform, entities in strings["entity"].items():
        for key, spec in entities.items():
            # "{collection}" alone would match any text at all
            if not re.sub(r"\{\w+\}", "", spec["name"]).strip():
                continue
            pattern = re.sub(r"\\\{\w+\\\}", ".+", re.escape(spec["name"]))
            names[f"{platform}.{key}"] = re.compile(pattern, re.IGNORECASE)
    return names


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_descriptions_name_entities_the_integration_creates(path):
    """Each blueprint says which sensor to pick in bold; that sensor has to exist."""
    description = load(path)["blueprint"]["description"]
    bold = re.findall(r"\*\*(.+?)\*\*", description)
    assert bold, "the description should name the sensor to pick in bold"

    names = entity_names()
    for name in bold:
        # "License … used percentage" stands for one sensor per license unit
        example = name.replace("…", "Instances")
        assert any(pattern.fullmatch(example) for pattern in names.values()), (
            f"**{name}** is not an entity the integration creates"
        )


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_notification_action_is_an_action_selector(path):
    """Hard-coding a notify service would tie the blueprint to one setup."""
    document = load(path)
    inputs = document["blueprint"]["input"]

    assert "notification_action" in inputs, "every blueprint should let the user choose"
    assert "action" in inputs["notification_action"]["selector"]


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_optional_inputs_have_defaults(path):
    """An input with no default is mandatory; that has to be deliberate."""
    document = load(path)

    mandatory = [
        name for name, spec in document["blueprint"]["input"].items() if "default" not in spec
    ]
    # The entities to watch and the action to run are the only things a user must supply
    allowed = {
        "alarm_sensors",
        "connected_sensors",
        "problem_sensors",
        "free_space_sensors",
        "forecast_sensors",
        "expiry_sensors",
        "usage_sensors",
        "notification_action",
    }
    assert set(mandatory) <= allowed, f"unexpectedly mandatory: {sorted(set(mandatory) - allowed)}"


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_recovery_actions_are_optional(path):
    """A recovery notification is a nice-to-have; nobody should be made to configure one."""
    inputs = load(path)["blueprint"]["input"]

    if "recovery_action" in inputs:
        assert inputs["recovery_action"]["default"] == []
        assert "action" in inputs["recovery_action"]["selector"]


def test_readme_links_every_blueprint():
    """A blueprint nobody can find is a blueprint nobody uses."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")

    assert "blueprint_url" in readme, "README should offer one-click import links"
    for path in blueprint_files():
        assert path.name in readme, f"{path.name} is not mentioned in the README"
        raw = "https%3A%2F%2Fraw.githubusercontent.com%2FCenvora%2Fha-veeam-one%2Fmain%2F"
        link = raw + path.relative_to(REPO).as_posix().replace("/", "%2F")
        assert link in readme, f"{path.name} has no working import link"


def test_hacs_declares_the_supported_home_assistant_version():
    """HACS blocks installation on older cores using this value."""
    hacs = json.loads((REPO / "hacs.json").read_text(encoding="utf-8"))

    major, minor = hacs["homeassistant"].split(".")[:2]
    assert (int(major), int(minor)) >= (2024, 10), (
        "blueprints use the plural trigger/action keys, which need 2024.10+"
    )


def test_the_integration_fires_no_events():
    """Veeam ONE has no bus events, so every blueprint watches entities instead.

    Should the integration start firing one, this is the reminder to give it a blueprint.
    """
    for path in INTEGRATION.glob("*.py"):
        assert "async_fire" not in path.read_text(encoding="utf-8"), path.name
    for path in blueprint_files():
        platforms = {entry["trigger"] for entry in load(path)["triggers"]}
        assert "event" not in platforms, f"{path.name} listens for an event nothing fires"


# Blueprints whose binary sensor triggers must never match a trip through unavailable
PINNED_BINARY_BLUEPRINTS = ("server_unreachable.yaml", "resource_problem.yaml")


@pytest.mark.parametrize("name", PINNED_BINARY_BLUEPRINTS)
def test_binary_sensor_triggers_pin_from_and_to(name):
    """A reload goes on -> unavailable -> on; only a trigger pinned both ways ignores that."""
    for entry in load(BLUEPRINT_DIR / name)["triggers"]:
        assert entry.get("from") in ("on", "off"), f"{entry} should pin from"
        assert entry.get("to") in ("on", "off"), f"{entry} should pin to"
        assert entry["from"] != entry["to"]


@pytest.mark.parametrize("name", PINNED_BINARY_BLUEPRINTS)
def test_recovery_only_follows_a_reported_problem(name):
    """A blip shorter than the delay raised no alert, so it must not raise a recovery."""
    text = (BLUEPRINT_DIR / name).read_text(encoding="utf-8")

    assert "trigger.from_state.last_changed" in text


NUMERIC_BLUEPRINTS = (
    "repository_space_low.yaml",
    "repository_out_of_space_forecast.yaml",
    "license_usage_high.yaml",
)


@pytest.mark.parametrize("name", NUMERIC_BLUEPRINTS)
def test_numeric_blueprints_require_a_numeric_previous_state(name):
    """numeric_state counts "unavailable -> 90" as crossing the threshold."""
    text = (BLUEPRINT_DIR / name).read_text(encoding="utf-8")

    assert "trigger.from_state is not none" in text
    assert "float(-1) >= 0" in text, "the previous state should have to be a real number"


def test_alarm_blueprint_survives_a_reload():
    """A reload drops the alarms attribute; coming back is not a batch of new alarms."""
    text = (BLUEPRINT_DIR / "alarm_triggered.yaml").read_text(encoding="utf-8")

    assert "trigger.from_state is not none" in text
    assert "unavailable" in text


def test_alarm_blueprint_reads_the_attribute_the_sensor_writes():
    """The keys the blueprint reads have to be the ones AlarmCountSensor writes."""
    sensor = source("sensor.py")
    text = (BLUEPRINT_DIR / "alarm_triggered.yaml").read_text(encoding="utf-8")

    assert '"alarms": [' in sensor
    assert "attributes.alarms" in text
    for key in ("id", "name", "status", "triggered", "object", "description"):
        assert f'"{key}":' in sensor, f"the sensor no longer writes {key}"
        assert f"alarm.{key}" in text or f"'{key}'" in text, f"the blueprint does not read {key}"


def test_alarm_blueprint_knows_the_attribute_cap():
    """While the list is full, alarms move in and out of it without being raised or resolved."""
    cap = re.search(r"^MAX_ALARM_ATTRIBUTES = (\d+)$", source("sensor.py"), re.MULTILINE)
    document = load(BLUEPRINT_DIR / "alarm_triggered.yaml")

    assert cap, "MAX_ALARM_ATTRIBUTES has moved"
    assert document["variables"]["max_listed"] == int(cap.group(1))


def test_alarm_blueprint_statuses_are_the_ones_counted_as_active():
    """Offering a status the Active alarms sensor never lists would be a dead option."""
    active = re.search(r"^ACTIVE_ALARM_STATUSES = \((.+)\)$", source("entity.py"), re.MULTILINE)
    statuses = load(BLUEPRINT_DIR / "alarm_triggered.yaml")["blueprint"]["input"]["statuses"]

    assert active, "ACTIVE_ALARM_STATUSES has moved"
    offered = {option["value"] for option in statuses["selector"]["select"]["options"]}
    assert offered == set(re.findall(r'"(\w+)"', active.group(1)))
    assert set(statuses["default"]) == offered


def test_alarm_blueprint_hands_over_what_resolve_alarm_needs():
    """The alarm IDs and config entry are the resolve_alarm action's two inputs."""
    services = yaml.safe_load(source("services.yaml"))
    document = load(BLUEPRINT_DIR / "alarm_triggered.yaml")

    assert {"alarm_ids", "config_entry_id"} <= set(services["resolve_alarm"]["fields"])
    assert {"alarm_ids", "entry_id"} <= set(document["variables"])
    assert "veeam_one.resolve_alarm" in document["blueprint"]["description"]


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_device_names_drop_the_veeam_one_prefix(path):
    """Resource devices are named "Veeam ONE <name>"; "Veeam ONE: Veeam ONE Nightly" reads badly.

    Only the device's own name is stripped: a name the user gave it is theirs.
    """
    assert 'name=f"{DEFAULT_NAME} {resource_name(' in source("entity.py")
    assert 'DEFAULT_NAME = "Veeam ONE"' in source("const.py")

    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r"device_attr\([^)]*'name'\)[^\n]*", text):
        assert "regex_replace('^Veeam ONE ', '')" in match.group(0), match.group(0)


def test_server_name_matches_the_config_entry_title():
    """The entry is titled "Veeam ONE (<host>)", and the blueprints slice the host out of it."""
    assert 'title=f"Veeam ONE ({' in source("config_flow.py")
    assert len("Veeam ONE (") == 11

    for name in ("alarm_triggered.yaml", "server_unreachable.yaml"):
        text = (BLUEPRINT_DIR / name).read_text(encoding="utf-8")
        assert "title.startswith('Veeam ONE (')" in text and "title[11:-1]" in text, name
