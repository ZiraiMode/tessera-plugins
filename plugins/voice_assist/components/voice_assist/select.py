"""A model-derived select; identity is the resolved YAML ID, never the option index."""
import hashlib

import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.components import font, micro_wake_word, select
from esphome.const import CONF_ID, CONF_MODEL, CONF_INTERNAL, CONF_FILE, CONF_GLYPHS
from esphome.core import CORE, ID
from . import WakePhraseSelect, voice_assist_ns

CONF_MICRO_WAKE_WORD_ID = "micro_wake_word_id"
WakeModelEntry = voice_assist_ns.struct("WakeModelEntry")
CONFIG_SCHEMA = select.select_schema(WakePhraseSelect).extend({
    cv.Required(CONF_MICRO_WAKE_WORD_ID): cv.use_id(micro_wake_word.MicroWakeWord),
}).extend(cv.COMPONENT_SCHEMA)


def option_labels(entries):
    """Disambiguate entire collision groups, including literal generated-label collisions."""
    labels = [entry["name"] for entry in entries]
    while len(set(labels)) != len(labels):
        counts = {label: labels.count(label) for label in labels}
        labels = [f"{label} [{entry['id']}]" if counts[label] > 1 else label
                  for entry, label in zip(entries, labels)]
    return labels


def screen_labels(full, entries, labels):
    ids = {"headline", "watch_value", "label", "sublabel", "sublabel_big"}
    configs = [item for item in full.get("font", []) if str(item[CONF_ID]) in ids]
    # Standalone packages need not include Tessera fonts. Their native entity labels stay genuine.
    available = len(configs) == len(ids)
    def drawable(label):
        return available and all(font.FONT_CACHE[item[CONF_FILE]].get_char_index(ord(char))
                                 for item in configs for char in label)
    projected = [label if drawable(label) else entry["id"] for entry, label in zip(entries, labels)]
    for item in configs:
        existing = set("".join(item[CONF_GLYPHS]))
        for extra in item[font.CONF_EXTRAS]:
            existing.update("".join(extra[CONF_GLYPHS]))
        for glyphset in item[font.CONF_GLYPHSETS]:
            existing.update(chr(point) for point in font.glyphsets.unicodes_per_glyphset(glyphset))
        missing = sorted(set("".join(projected)) - existing)
        if missing:
            item[CONF_GLYPHS].extend(missing)
            font.validate_font_config(item)
    return projected


def final_validate(config):
    full = fv.full_config.get()
    path = full.get_path_for_id(config[CONF_MICRO_WAKE_WORD_ID])[:-1]
    wake = full.get_config_for_path(path)
    entries = []
    timing = None
    parameters = list(wake["models"])
    if wake.get("vad") is not None:
        parameters.append(wake["vad"])
    for parameters_ in parameters:
        manifest, _ = micro_wake_word._model_config_to_manifest_data(parameters_[CONF_MODEL])
        name = manifest["wake_word"]
        step = manifest["micro"]["feature_step_size"]
        model_id = str(parameters_[CONF_ID])
        if step <= 0:
            raise cv.Invalid(f"Wake model {model_id} ({name}) has a nonpositive feature step size")
        if timing is not None and timing != step:
            raise cv.Invalid(f"Wake model {model_id} ({name}) uses {step}ms, expected {timing}ms (including VAD)")
        timing = step
        if name == "vad" or parameters_.get(CONF_INTERNAL, False):
            continue
        if not name.strip():
            raise cv.Invalid(f"Wake model {model_id} has an empty wake phrase")
        entries.append({"id": model_id, "model_id": parameters_[CONF_ID], "name": name})
    if len(entries) > 255:
        raise cv.Invalid("Wake phrase supports at most 255 selectable models")
    labels = option_labels(entries)
    projected = screen_labels(full, entries, labels)
    for entry, label, projection in zip(entries, labels, projected):
        entry.update(label=label, screen_label=projection)
    CORE.data.setdefault("voice_assist", {}).setdefault("wake_models", {})[str(config[CONF_ID])] = entries
    return config


FINAL_VALIDATE_SCHEMA = final_validate


async def to_code(config):
    entries = CORE.data["voice_assist"]["wake_models"][str(config[CONF_ID])]
    var = cg.new_Pvariable(config[CONF_ID])
    await select.register_select(var, config, options=[entry["label"] for entry in entries])
    await cg.register_component(var, config)
    if not entries:
        cg.add(var.set_models(cg.nullptr, 0))
        return
    rows = []
    for entry in entries:
        model = await cg.get_variable(entry["model_id"])
        identity = cg.ArrayInitializer(*hashlib.sha256(entry["id"].encode()).digest())
        rows.append(cg.StructInitializer(WakeModelEntry, ("model", model),
                                         ("identity", identity), ("screen_label", entry["screen_label"])))
    table = cg.static_const_array(ID(f"{config[CONF_ID]}_models", is_declaration=True, type=WakeModelEntry),
                                 cg.ArrayInitializer(*rows))
    cg.add(var.set_models(table, len(entries)))
