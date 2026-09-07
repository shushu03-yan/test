# RASPA 模拟参数整理包

本文件夹是从超算项目 `/gpfs/work/che/qitaiwu23/shushu/raspa` 中整理出来的自包含设置包，
包含单组分/混合组分 GCMC 与吸附位点筛选所需的全部输入与工作流脚本，可整体复制到本地查看或复用。

## 目录结构

```text
simulation_settings/
├── README.md                        本文档
├── configs/                         RASPA 工作流配置模板（JSON）
├── forcefield/                      力场参数（RASPA .def）
├── molecules/                       分子定义（RASPA .def）
├── frameworks/                      结构框架（CIF + 柔性框架定义）
├── example_simulation_input/        由配置实际生成的 simulation.input 示例
├── workflow/                        生成/提交/查询/汇总脚本（含 raspa_workflow 包）
└── results/                         一组示例汇总结果（CSV）
```

## 各目录说明

### configs/

- `single_config.json`：实际运行的刚性单组分 GCMC。吸附质 N2，77 K，10 个相对压力点
  （P0 ≈ 97313.45 Pa，对应 0.1–1.0 P/P0），初始化/生产各 100000 循环，cutoff 12 Å，
  超胞最小边长 24 Å，Ewald 精度 1e-6，孔体积分数 0.4661847。
- `single_config_labelnorm.json`：与 single 相同，仅 campaign 名不同，
  用于带 `RemoveAtomNumberCodeFromLabel` 标签归一化的对照运行。
- `mix_config.json`：混合组分模板（示例为 Xe/Kr = 0.2/0.8，298 K）。
- `minimization_config.json`：单分子吸附位点能量筛选模板（需要开启 Movies）。

### forcefield/

- `force_field.def`：全为 0，不覆盖内置规则。
- `pseudo_atoms.def`：35 个伪原子。N2 采用三点 TraPPE 模型（两个 N_n2，电荷 −0.482；
  一个无质量的 N_com，电荷 +0.964）；He/Ar/Kr/Xe 为单原子。
- `force_field_mixing_rules.def`：约 139 条 LJ 参数 + 混合规则。
  吸附质如 N_n2（ε=36.0 K, σ=3.31 Å），框架原子用 DREIDING 元素参数（C_/H_/O_/N_ 等），
  截断 `truncated`、关 tail correction，混合采用 Lorentz-Berthelot。

### molecules/

各吸附质分子的 .def：N2（刚性 3 点）、argon/krypton/xenon/helium（单原子），以及 none。

### frameworks/

- `INT1-sxrd.cif`：正交 P1 结构，a=23.79, b=10.636, c=34.52 Å（α=β=γ=90°），
  原子带净电荷（电荷取自 CIF）。运行时会按 24 Å 超胞自动放大为 `UnitCells 2 3 1`。
- `Dubbeldam2007FlexibleIRMOF-1/framework.def`：IRMOF-1/MOF-5 柔性框架定义
  （harmonic 键/键角 + TraPPE 二面角）。当前 single/mix 配置 `flexible.enabled=false`，
  该文件暂未启用，仅作为柔性运行的预留。

### example_simulation_input/

- `single_N2_77K_P0.5.simulation.input`：单组分 N2/77 K/48656.725 Pa（P/P0=0.5）实际生成的输入。
- `void_fraction_helium.simulation.input`：用氦 Widom 方法计算孔体积分数的输入。

### workflow/

生成、提交与汇总脚本：

```bash
python3 validate_config.py --config configs/single_config.json
python3 prepare_jobs.py --config configs/single_config.json
python3 submit_jobs.py --run runs/single/<campaign>
python3 check_jobs.py --run runs/single/<campaign>
python3 collect_results.py --run runs/single/<campaign>
```

`raspa_workflow/` 为共享 Python 包：`config.py` 校验配置、`render.py` 渲染 simulation.input、
`campaign.py` 生成任务与超胞、`cif.py` 读取晶胞并计算超胞倍数、`worker.py` 执行 simulate。

## 主要参数速查

| 参数 | 当前值 | 说明 |
|---|---|---|
| 框架 | INT1-sxrd | 刚性，电荷取自 CIF |
| 吸附质 | N2 | TraPPE 三点模型 |
| 温度 | 77 K | —
| 压力范围 | 9731.345–97313.45 Pa | 0.1–1.0 P/P0 |
| Initialization/Production | 100000 / 100000 | — |
| CutOff | 12.0 Å | — |
| EwaldPrecision | 1e-6 | — |
| 超胞 | 2 3 1 | 由 24 Å 最小边长自动计算 |
| HeliumVoidFraction | 0.4661847 | — |
| 混合规则 | Lorentz-Berthelot | 截断 truncated，关 tail correction |

> 注意：GCMC 默认关闭 Movies/VTK；建议在计算节点而非登录节点运行 `simulate`。
