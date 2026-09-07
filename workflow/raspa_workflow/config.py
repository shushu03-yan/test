from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

WORKFLOWS = {"single", "mix", "minimization"}
CAMPAIGN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FORCEFIELD_FILES = (
    "force_field.def",
    "force_field_mixing_rules.def",
    "pseudo_atoms.def",
)


class ConfigError(ValueError):
    pass


def project_root_for(config_path: Path) -> Path:
    config_path = config_path.resolve()
    return config_path.parent.parent if config_path.parent.name == "configs" else Path.cwd().resolve()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def _number_list(value: Any, name: str, *, positive: bool = True) -> list[float]:
    _require(isinstance(value, list) and value, f"{name} 必须是非空数组")
    result = []
    for item in value:
        _require(isinstance(item, (int, float)) and not isinstance(item, bool), f"{name} 必须只包含数字")
        number = float(item)
        _require(math.isfinite(number), f"{name} 包含非有限数字")
        if positive:
            _require(number > 0, f"{name} 必须大于 0")
        result.append(number)
    return result


def load_and_validate(config_path: str | Path) -> tuple[dict[str, Any], Path]:
    path = Path(config_path).resolve()
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"JSON 格式错误 {path}:{exc.lineno}: {exc.msg}") from exc

    _require(isinstance(cfg, dict), "配置顶层必须是对象")
    _require(cfg.get("schema_version") == 1, "schema_version 必须为 1")
    campaign = cfg.get("campaign")
    _require(isinstance(campaign, str) and CAMPAIGN_RE.fullmatch(campaign) is not None,
             "campaign 只能包含字母、数字、点、下划线和连字符")
    workflow = cfg.get("workflow")
    _require(workflow in WORKFLOWS, f"workflow 必须为 {sorted(WORKFLOWS)} 之一")

    root = project_root_for(path)
    paths = cfg.get("paths", {})
    _require(isinstance(paths, dict), "paths 必须是对象")
    for key in ("structures", "forcefield", "molecules"):
        _require(isinstance(paths.get(key), str) and paths[key], f"paths.{key} 必须是路径字符串")
    structures = (root / paths["structures"]).resolve()
    forcefield = (root / paths["forcefield"]).resolve()
    molecules = (root / paths["molecules"]).resolve()
    _require(structures.is_dir(), f"结构目录不存在: {structures}")
    _require(any(structures.glob("*.cif")), f"结构目录中没有 .cif: {structures}")
    _require(forcefield.is_dir(), f"力场目录不存在: {forcefield}")
    for filename in FORCEFIELD_FILES:
        _require((forcefield / filename).is_file(), f"缺少力场文件: {forcefield / filename}")
    _require(molecules.is_dir(), f"分子目录不存在: {molecules}")

    simulation = cfg.get("simulation", {})
    _require(isinstance(simulation, dict), "simulation 必须是对象")
    _number_list(simulation.get("temperatures"), "simulation.temperatures")
    cutoff = simulation.get("cutoff", 12.0)
    _require(isinstance(cutoff, (int, float)) and cutoff > 0, "simulation.cutoff 必须大于 0")
    spacing = simulation.get("supercell_min_length", 2 * float(cutoff))
    _require(isinstance(spacing, (int, float)) and spacing >= 2 * float(cutoff),
             "simulation.supercell_min_length 必须至少为 2 × cutoff")
    for name in ("initialization_cycles", "production_cycles", "print_every"):
        value = simulation.get(name)
        _require(isinstance(value, int) and value >= 0, f"simulation.{name} 必须是非负整数")
    if workflow != "minimization":
        _number_list(simulation.get("pressures"), "simulation.pressures")

    outputs = cfg.get("outputs", {})
    _require(isinstance(outputs, dict), "outputs 必须是对象")
    for name in ("movies", "vtk"):
        _require(isinstance(outputs.get(name, False), bool), f"outputs.{name} 必须是布尔值")
    if workflow == "minimization":
        _require(outputs.get("movies") is True, "位点筛选必须设置 outputs.movies=true")

    resources = cfg.get("resources", {})
    _require(isinstance(resources, dict), "resources 必须是对象")
    for name in ("partition", "qos", "time", "memory"):
        _require(isinstance(resources.get(name), str) and resources[name], f"resources.{name} 必须是字符串")
    for name in ("cpus_per_task", "max_concurrent"):
        _require(isinstance(resources.get(name), int) and resources[name] > 0,
                 f"resources.{name} 必须是正整数")

    if workflow in {"single", "minimization"}:
        adsorbates = cfg.get("adsorbates")
        _require(isinstance(adsorbates, list) and adsorbates and all(isinstance(x, str) and x for x in adsorbates),
                 "adsorbates 必须是非空字符串数组")
        _require(len(set(adsorbates)) == len(adsorbates), "adsorbates 不能重复")
        molecule_names = adsorbates
    else:
        mixtures = cfg.get("mixtures")
        _require(isinstance(mixtures, list) and mixtures, "mixtures 必须是非空数组")
        molecule_names = []
        seen_names: set[str] = set()
        for index, mixture in enumerate(mixtures):
            _require(isinstance(mixture, dict), f"mixtures[{index}] 必须是对象")
            name = mixture.get("name")
            _require(isinstance(name, str) and CAMPAIGN_RE.fullmatch(name or "") is not None,
                     f"mixtures[{index}].name 无效")
            _require(name not in seen_names, f"混合物名称重复: {name}")
            seen_names.add(name)
            components = mixture.get("components")
            fractions = mixture.get("fractions")
            _require(isinstance(components, list) and len(components) >= 2 and
                     all(isinstance(x, str) and x for x in components),
                     f"mixtures[{index}].components 至少包含两个分子")
            _require(len(set(components)) == len(components), f"mixtures[{index}] 组分不能重复")
            parsed_fractions = _number_list(fractions, f"mixtures[{index}].fractions")
            _require(len(parsed_fractions) == len(components), f"mixtures[{index}] 组分与比例数量不一致")
            _require(abs(sum(parsed_fractions) - 1.0) <= 1e-8, f"mixtures[{index}] 摩尔分数之和必须为 1")
            molecule_names.extend(components)

    for molecule in set(molecule_names):
        _require((molecules / f"{molecule}.def").is_file(), f"缺少分子定义: {molecules / (molecule + '.def')}")

    flexible = cfg.get("flexible", {"enabled": False})
    _require(isinstance(flexible, dict) and isinstance(flexible.get("enabled", False), bool),
             "flexible.enabled 必须是布尔值")
    if flexible.get("enabled"):
        _require(workflow in {"single", "mix"}, "位点筛选不支持 flexible.enabled")
        definitions = flexible.get("framework_definitions")
        _require(isinstance(definitions, dict), "柔性模拟需要 flexible.framework_definitions 映射")
        for cif in structures.glob("*.cif"):
            rel = definitions.get(cif.stem)
            _require(isinstance(rel, str), f"柔性框架 {cif.stem} 缺少 framework.def 映射")
            _require((root / rel).resolve().is_file(), f"柔性框架定义不存在: {(root / rel).resolve()}")
        steps = flexible.get("hybrid_nve_steps", 5)
        _require(isinstance(steps, int) and steps > 0, "flexible.hybrid_nve_steps 必须为正整数")
        time_step = flexible.get("time_step", 0.0005)
        _require(isinstance(time_step, (int, float)) and time_step > 0,
                 "flexible.time_step 必须大于 0")

    supercells = cfg.get("supercells", {})
    _require(isinstance(supercells, dict), "supercells 必须是对象")
    for framework, cells in supercells.items():
        _require(isinstance(cells, list) and len(cells) == 3 and
                 all(isinstance(x, int) and x > 0 for x in cells),
                 f"supercells.{framework} 必须是三个正整数")

    return cfg, root
