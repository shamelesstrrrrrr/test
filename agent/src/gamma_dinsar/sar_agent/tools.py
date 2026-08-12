from __future__ import annotations

from pathlib import Path
from typing import Any
from notifier import notify_from_inputs
import yaml

from src.gamma_dinsar.beiy.workflow import S1PreprocessingWorkflow
from executor import LocalCommandExecutor
from task_defaults import (
    apply_derived_codes,
    apply_derived_paths,
    describe_code_defaults,
    describe_effective_inputs,
    minimal_config_template,
    missing_required_inputs,
    resolve_effective_inputs,
)


class AgentTools:
    def __init__(self) -> None:
        self.workflow = S1PreprocessingWorkflow()

    def update_task_info(self, **kwargs: Any) -> str:
        result = self.workflow.update_inputs(**kwargs)

        if "输入无效" in result:
            return result

        missing = missing_required_inputs(dict(self.workflow.status()["inputs"]))
        if missing:
            return "已更新任务信息。\n当前还缺少：" + ", ".join(missing)

        return (
            "任务基础参数已完整。\n"
            "未提供的算法参数将使用代码默认值；可调用 get_effective_task_parameters 查看最终参数。"
        )

    def validate_task_info(self) -> str:
        return self.workflow.validate()

    def get_task_status(self) -> str:
        return yaml.safe_dump(
            self.workflow.status(),
            allow_unicode=True,
            sort_keys=False,
        )

    def get_default_parameters(self) -> str:
        return describe_code_defaults()

    def get_effective_task_parameters(self) -> str:
        return describe_effective_inputs(dict(self.workflow.status()["inputs"]))

    def write_yaml_config(self, config_path: str) -> str:
        path = Path(config_path).expanduser()

        if path.exists():
            return f"配置文件已存在，为避免覆盖已停止写入：{path}"

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(
                minimal_config_template(),
                handle,
                allow_unicode=True,
                sort_keys=False,
            )

        return (
            f"已写入紧凑配置模板：{path}\n"
            "模板包含用户必须提供的字段和关键处理路线选择；高级数值参数由代码默认值提供。"
        )

    def load_task_config(self, config_path: str) -> str:
        path = Path(config_path).expanduser()

        if not path.exists():
            return f"配置文件不存在：{path}"

        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        result = self.workflow.update_inputs(**data)
        if "输入无效" in result:
            return result

        return (
            f"配置文件已读取：{path}\n"
            "配置字段已载入；本次运行范围由 workflow_start/workflow_end 控制。\n"
            "已应用代码默认参数；用户在配置文件中提供的字段会覆盖默认值。\n"
            "如需查看当前实际采用的参数，请调用 get_effective_task_parameters。"
        )

    def _resolve_templates(self, data: dict[str, Any]) -> dict[str, Any]:
        resolved = dict(data)

        master_date = resolved.get("master_date")
        if not master_date:
            return resolved

        variables = {
            "master_date": str(master_date),
        }

        for key, value in list(resolved.items()):
            if isinstance(value, str):
                for var_name, var_value in variables.items():
                    value = value.replace("{" + var_name + "}", var_value)
                resolved[key] = value

        return resolved

    def _inputs(self) -> dict[str, Any]:
        inputs = dict(self.workflow.status()["inputs"])
        inputs = resolve_effective_inputs(inputs)
        inputs = self._resolve_templates(inputs)
        return inputs

    def _apply_default_paths(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return apply_derived_codes(apply_derived_paths(inputs))

    def _executor(self) -> LocalCommandExecutor:
        inputs = self._inputs()
        return LocalCommandExecutor(env_scripts=inputs.get("env_scripts", []))

    def run_unzip_s1_real(self) -> str:
        inputs = self._inputs()

        required = ["raw_zip_dir", "unzip_dir"]
        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "解压缺少参数：" + ", ".join(missing)

        return self._executor().run_unzip_s1(
            raw_zip_dir=inputs["raw_zip_dir"],
            unzip_dir=inputs["unzip_dir"],
        )

    def run_generate_slc_real(self) -> str:
        inputs = self._inputs()

        required = [
            "unzip_dir",
            "satellite_code",
            "polarization_code",
            "swath_code",
        ]
        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "生成 SLC 缺少参数：" + ", ".join(missing)

        return self._executor().run_generate_slc(
            unzip_dir=inputs["unzip_dir"],
            satellite_code=inputs["satellite_code"],
            polarization_code=inputs["polarization_code"],
            swath_code=inputs["swath_code"],
        )

    def run_extract_burst_real(self) -> str:
        inputs = self._inputs()

        required = [
            "unzip_dir",
            "burst_dir",
            "polarization_code",
            "swath_code",
            "bn_start1",
            "bn_end1",
        ]
        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "提取 burst 缺少参数：" + ", ".join(missing)

        return self._executor().run_extract_burst_multi_from_unzip_dir(
            unzip_dir=inputs["unzip_dir"],
            burst_dir=inputs["burst_dir"],
            polarization_code=inputs["polarization_code"],
            swath_code=inputs["swath_code"],
            bn_start1="" if inputs.get("bn_start1") is None else str(inputs.get("bn_start1")),
            bn_end1="" if inputs.get("bn_end1") is None else str(inputs.get("bn_end1")),
            bn_start2="" if inputs.get("bn_start2") is None else str(inputs.get("bn_start2")),
            bn_end2="" if inputs.get("bn_end2") is None else str(inputs.get("bn_end2")),
            bn_start3="" if inputs.get("bn_start3") is None else str(inputs.get("bn_start3")),
            bn_end3="" if inputs.get("bn_end3") is None else str(inputs.get("bn_end3")),
        )

    def run_preprocessing_until_burst(self) -> str:
        inputs = self._inputs()
        logs: list[str] = []

        if inputs.get("skip_unzip", False):
            logs.append("跳过解压：skip_unzip=true")
        else:
            logs.append(self.run_unzip_s1_real())

        if inputs.get("skip_generate_slc", False):
            logs.append("跳过生成 SLC：skip_generate_slc=true")
        else:
            logs.append(self.run_generate_slc_real())

        if inputs.get("skip_extract_burst", False):
            logs.append("跳过 burst 提取：skip_extract_burst=true")
        else:
            logs.append(self.run_extract_burst_real())

        return "\n\n".join(logs)
    ################地理编码############################
    def run_slc_geo_real(self) -> str:
        inputs = self._inputs()

        required = [
            "geo_dir",
            "slc_file",
            "dem_file",
        ]
        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "地理编码缺少参数：" + ", ".join(missing)

        return self._executor().run_slc_geo(
            geo_dir=inputs["geo_dir"],
            slc_file=inputs["slc_file"],
            dem_file=inputs["dem_file"],
            range_looks=str(inputs.get("range_looks", "1")),
            azimuth_looks=str(inputs.get("azimuth_looks", "1")),
            lat_ovr=str(inputs.get("lat_ovr", "5")),
            lon_ovr=str(inputs.get("lon_ovr", "5")),
        )
    ###############影像配准################
    def run_slc_coreg_multi_real(self) -> str:
        inputs = self._inputs()

        required = [
            "burst_dir",
            "geo_dir",
            "list_file",
            "polarization",
            "swath",
            "coreg_dir",
        ]
        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "影像配准缺少参数：" + ", ".join(missing)

        polarization_map = {
            "VV": "0",
            "0": "0",
            "VH": "1",
            "1": "1",
        }

        swath_map = {
            "IW1": "1",
            "1": "1",
            "IW2": "2",
            "2": "2",
            "IW3": "3",
            "3": "3",
            "IW1+IW2": "4",
            "4": "4",
            "IW1+IW3": "5",
            "5": "5",
            "IW2+IW3": "6",
            "6": "6",
            "IW1+IW2+IW3": "7",
            "7": "7",
        }

        polarization_key = str(inputs["polarization"]).strip().upper()
        swath_key = str(inputs["swath"]).strip().upper().replace(" ", "")

        if polarization_key not in polarization_map:
            return f"影像配准失败：polarization 参数无效：{inputs['polarization']}，可选 VV/VH/0/1"

        if swath_key not in swath_map:
            return (
                f"影像配准失败：swath 参数无效：{inputs['swath']}，"
                "可选 IW1/IW2/IW3/IW1+IW2/IW1+IW3/IW2+IW3/IW1+IW2+IW3"
            )

        polarization_code = polarization_map[polarization_key]
        swath_code = swath_map[swath_key]

        return self._executor().run_slc_coreg_multi(
            burst_dir=inputs["burst_dir"],
            geo_dir=inputs["geo_dir"],
            list_file=inputs["list_file"],
            polarization=polarization_code,
            swath=swath_code,
            coreg_dir=inputs["coreg_dir"],
        )
#################影像裁剪########################
    def run_slc_copy_crop_all_real(self) -> str:
        inputs = self._inputs()

        if not inputs.get("enable_crop", True):
            return "跳过裁剪：enable_crop=false"

        required = [
            "list_file",
            "coreg_dir",
            "crop_dir",
            "master_date",
            "swath",
            "polarization",
            "crop_roff",
            "crop_nr",
            "crop_loff",
            "crop_nl",
        ]

        missing = [key for key in required if not inputs.get(key)]
        if missing:
            return "裁剪缺少参数：" + ", ".join(missing)

        return self._executor().run_slc_copy_crop_all(
            list_file=str(inputs["list_file"]),
            coreg_dir=str(inputs["coreg_dir"]),
            crop_dir=str(inputs["crop_dir"]),
            master_date=str(inputs["master_date"]),
            swath=str(inputs.get("swath", "IW1")),
            polarization=str(inputs.get("polarization", "VV")),
            data_format=str(inputs.get("data_format", "-")),
            scale_factor=str(inputs.get("scale_factor", "-")),
            crop_roff=str(inputs["crop_roff"]),
            crop_nr=str(inputs["crop_nr"]),
            crop_loff=str(inputs["crop_loff"]),
            crop_nl=str(inputs["crop_nl"]),
        )
######################生成rslc_tab文件#######################
    def write_rslc_tab_from_list_real(self) -> str:
        inputs = self._inputs()

        required = [
            "list_file",
            "rslc_dir",
            "rslc_tab",
        ]
        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "生成 RSLC_tab 缺少参数：" + ", ".join(missing)

        return self._executor().write_rslc_tab_from_list(
            list_file=inputs["list_file"],
            rslc_dir=inputs["rslc_dir"],
            rslc_tab=inputs["rslc_tab"],
            rslc_template=str(inputs.get("rslc_template", "$1/$1.rslc")),
            rslc_par_template=str(inputs.get("rslc_par_template", "$1/$1.rslc.par")),
        )
    #############生成itab文件####################
    def run_base_calc_itab_real(self) -> str:
        inputs = self._inputs()

        required = [
            "rslc_tab",
            "master_rslc_par",
            "bperp_file",
            "itab_file",
        ]
        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "生成 itab 缺少参数：" + ", ".join(missing)

        return self._executor().run_base_calc_itab(
            rslc_tab=inputs["rslc_tab"],
            master_rslc_par=inputs["master_rslc_par"],
            bperp_file=inputs["bperp_file"],
            itab_file=inputs["itab_file"],
            itab_type=str(inputs.get("itab_type", "1")),
            plot_flag=str(inputs.get("base_calc_plot_flag", "1")),
            bperp_min=str(inputs.get("bperp_min", "-")),
            bperp_max=str(inputs.get("bperp_max", "200")),
            delta_t_min=str(inputs.get("delta_t_min", "-")),
            delta_t_max=str(inputs.get("delta_t_max", "37")),
            delta_n_max=str(inputs.get("delta_n_max", "2")),
        )
#######################3生成RMLI强度文件##################
    def run_mk_mli_all_real(self) -> str:
        inputs = self._inputs()

        required = [
            "rslc_tab",
            "rmli_dir",
        ]
        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "生成 RMLI 缺少参数：" + ", ".join(missing)

        return self._executor().run_mk_mli_all(
            rslc_tab=inputs["rslc_tab"],
            rmli_dir=inputs["rmli_dir"],
            rlks=str(inputs.get("rlks", "5")),
            azlks=str(inputs.get("azlks", "1")),
        )
    ###############差分干涉################
    def run_diff_workflow_real(self) -> str:
        inputs = self._inputs()

        required = [
            "diff_geo_dir",
            "diff_master_rslc",
            "dem_file",
            "rslc_tab",
            "itab_file",
            "sar_dem",
            "master_rmli",
            "rmli_dir",
            "diff_dir",
            "diff_method",
        ]
        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "生成差分干涉图缺少参数：" + ", ".join(missing)

        method = str(inputs.get("diff_method", "initial")).strip().lower()

        logs: list[str] = []

        logs.append("### 1. 对裁剪后的干涉主影像重新地理编码")
        geo_result = self._executor().run_slc_geo(
            geo_dir=inputs["diff_geo_dir"],
            slc_file=inputs["diff_master_rslc"],
            dem_file=inputs["dem_file"],
            range_looks=str(inputs.get("rlks", "5")),
            azimuth_looks=str(inputs.get("azlks", "1")),
            lat_ovr=str(inputs.get("lat_ovr", "5")),
            lon_ovr=str(inputs.get("lon_ovr", "5")),
        )
        logs.append(geo_result)

        if geo_result.startswith(("SLC 地理编码失败。", "SLC 地理编码未启动：")):
            return "\n\n".join(logs)

        logs.append(f"### 2. 生成差分干涉图，方法：{method}")

        if method == "initial":
            logs.append(
                self._executor().run_mk_diff_2d_initial(
                    rslc_tab=inputs["rslc_tab"],
                    itab_file=inputs["itab_file"],
                    sar_dem=inputs["sar_dem"],
                    master_rmli=inputs["master_rmli"],
                    rmli_dir=inputs["rmli_dir"],
                    diff_dir=inputs["diff_dir"],
                    rlks=str(inputs.get("rlks", "5")),
                    azlks=str(inputs.get("azlks", "1")),
                    diff_param_1=str(inputs.get("diff_param_1", "3")),
                    s_value=str(inputs.get("diff_s_value", "2")),
                    e_value=str(inputs.get("diff_e_value", "0.1")),
                )
            )

        elif method == "fourier":
            logs.append(
                self._executor().run_mk_diff_2d_fourier_refine(
                    rslc_tab=inputs["rslc_tab"],
                    itab_file=inputs["itab_file"],
                    sar_dem=inputs["sar_dem"],
                    master_rmli=inputs["master_rmli"],
                    rmli_dir=inputs["rmli_dir"],
                    diff_dir=inputs["diff_dir"],
                    rlks=str(inputs.get("rlks", "5")),
                    azlks=str(inputs.get("azlks", "1")),
                    diff_param_1=str(inputs.get("diff_param_1", "3")),
                    s_value=str(inputs.get("diff_s_value", "2")),
                    e_value=str(inputs.get("diff_e_value", "0.1")),
                )
            )

        elif method == "unwrapped_ls":
            required_extra = [
                "diff2_dir",
                "pbase_file",
            ]
            missing_extra = [key for key in required_extra if not inputs.get(key)]

            if missing_extra:
                return "解缠相位最小二乘方法缺少参数：" + ", ".join(missing_extra)

            logs.append(
                self._executor().run_mk_diff_2d_unw_refine(
                    rslc_tab=inputs["rslc_tab"],
                    itab_file=inputs["itab_file"],
                    sar_dem=inputs["sar_dem"],
                    master_rmli=inputs["master_rmli"],
                    rmli_dir=inputs["rmli_dir"],
                    diff_dir=inputs["diff_dir"],
                    diff2_dir=inputs["diff2_dir"],
                    pbase_file=inputs["pbase_file"],
                    rlks=str(inputs.get("rlks", "5")),
                    azlks=str(inputs.get("azlks", "1")),
                    diff_param_1=str(inputs.get("diff_param_1", "3")),
                    s_value=str(inputs.get("diff_s_value", "2")),
                    e_value=str(inputs.get("diff_e_value", "0.1")),
                    adf_alpha=str(inputs.get("adf_alpha", "0.35")),
                    adf_window=str(inputs.get("adf_window", "32")),
                    unw_alpha=str(inputs.get("unw_alpha", "0.35")),
                )
            )

        else:
            return (
                "diff_method 参数无效。可选值："
                "initial, fourier, unwrapped_ls"
            )

        return "\n\n".join(logs)
    #############同质点选取##############
    def run_select_shp_matlab_real(self) -> str:
        inputs = self._inputs()

        required = [
            "rmli_dir",
            "rmli_par",
            "shp_output_dir",
            "matlab_work_dir",
            "matlab_func_dir",
        ]

        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "SHP选点缺少参数：" + ", ".join(missing)

        return self._executor().run_select_shp_matlab(
            rmli_dir=inputs["rmli_dir"],
            rmli_par=inputs["rmli_par"],
            shp_output_dir=inputs["shp_output_dir"],
            matlab_work_dir=inputs["matlab_work_dir"],
            matlab_func_dir=inputs["matlab_func_dir"],
            cal_win_range=str(inputs.get("cal_win_range", "15")),
            cal_win_azimuth=str(inputs.get("cal_win_azimuth", "15")),
            alpha=str(inputs.get("alpha", "0.05")),
            shp_method=str(inputs.get("shp_method", "HTCI")),
            matlab_command=str(inputs.get("matlab_command", "matlab")),
        )
    ##############相位优化################
    def run_phase_optimization_workflow_real(self) -> str:
        inputs = self._inputs()

        required = [
            "diff_dir",
            "phase_opt_output_dir",
            "matlab_work_dir",
            "matlab_func_dir",
            "phase_opt_method",
            "fit_threshold",
            "shp_output_dir",
            "shp_method",
        ]

        missing = [key for key in required if not inputs.get(key)]

        if missing:
            return "2.6 相位优化缺少参数：" + ", ".join(missing)

        return self._executor().run_phase_optimization_workflow(
            diff_dir=inputs["diff_dir"],
            phase_opt_output_dir=inputs["phase_opt_output_dir"],
            matlab_work_dir=inputs["matlab_work_dir"],
            matlab_func_dir=inputs["matlab_func_dir"],
            phase_opt_method=str(inputs["phase_opt_method"]),
            fit_threshold=str(inputs["fit_threshold"]),
            shp_output_dir=inputs["shp_output_dir"],
            shp_method=str(inputs["shp_method"]),
            ref_id=str(inputs.get("ref_id", "1")),
            block_size=str(inputs.get("block_size", "1")),
            matlab_command=str(inputs.get("matlab_command", "matlab")),
            output_name=str(inputs.get("phase_opt_output_name", "phase_opt")),
        )
    #########数据整理##################
    def run_file_construct_real(self) -> str:
        inputs = self._inputs()

        required_values = {
            "diff_geo_dir": inputs.get("diff_geo_dir"),
            "rslc_dir/crop_dir": inputs.get("rslc_dir") or inputs.get("crop_dir"),
            "diff_dir": inputs.get("diff_dir"),
            "phase_opt_output_dir": inputs.get("phase_opt_output_dir"),
            "list_file": inputs.get("list_file"),
            "bperp_file": inputs.get("bperp_file"),
            "rmli_dir": inputs.get("rmli_dir"),
            "ts_flag": inputs.get("ts_flag"),
            "master_date": inputs.get("master_date"),
        }

        missing = [key for key, value in required_values.items() if not value]

        if missing:
            return "file_construct 缺少参数：" + ", ".join(missing)

        return self._executor().run_file_construct(
            geo_dir=inputs["diff_geo_dir"],
            ts_flag=str(inputs["ts_flag"]),
            rslc_dir=inputs.get("rslc_dir") or inputs["crop_dir"],
            diff_dir=inputs["diff_dir"],
            phase_opt_output_dir=inputs["phase_opt_output_dir"],
            list_file=inputs["list_file"],
            bperp_file=inputs["bperp_file"],
            rmli_dir=inputs["rmli_dir"],
            master_date=str(inputs["master_date"]),
        )
    ###############psc选点####################
    def run_mt_prep_gamma_real(self) -> str:
        inputs = self._inputs()

        ts_dir = Path(inputs["phase_opt_output_dir"]) / "TS"

        if str(inputs.get("ts_flag", "1")) == "0":
            default_da = "0.4"
        else:
            default_da = "0.6"

        required_values = {
            "master_date": inputs.get("master_date"),
            "phase_opt_output_dir": inputs.get("phase_opt_output_dir"),
            "ts_flag": inputs.get("ts_flag"),
        }

        missing = [key for key, value in required_values.items() if not value]

        if missing:
            return "mt_prep_gamma 缺少参数：" + ", ".join(missing)

        return self._executor().run_mt_prep_gamma(
            master_date=str(inputs["master_date"]),
            ts_dir=str(ts_dir),
            ts_flag=str(inputs.get("ts_flag", "1")),
            da_thresh=str(inputs.get("psc_da_thresh", default_da)),
            rg_patches=str(inputs.get("rg_patches", "1")),
            az_patches=str(inputs.get("az_patches", "1")),
            rg_overlap=str(inputs.get("rg_overlap", "50")),
            az_overlap=str(inputs.get("az_overlap", "50")),
            mask_file=inputs.get("mask_file"),
        )
    ##############dsc和dsps融合################
    # def run_dsc_pds_workflow_real(self) -> str:
    #     inputs = self._inputs()
    #
    #     phase_opt_output_name = str(inputs.get("phase_opt_output_name", "phase_opt"))
    #     phase_opt_mat = (
    #             Path(inputs["phase_opt_output_dir"]) / f"{phase_opt_output_name}.mat"
    #     )
    #     ts_dir = Path(inputs["phase_opt_output_dir"]) / "TS"
    #
    #     mt_prep_gamma_addds_command = str(
    #         inputs.get("mt_prep_gamma_addds_command", "mt_prep_gamma_addDS")
    #     ),
    #
    #     required_values = {
    #         "master_date": inputs.get("master_date"),
    #         "phase_opt_output_dir": inputs.get("phase_opt_output_dir"),
    #         "diff_dir": inputs.get("diff_dir"),
    #         "matlab_work_dir": inputs.get("matlab_work_dir"),
    #         "matlab_func_dir": inputs.get("matlab_func_dir"),
    #         "fit_threshold": inputs.get("fit_threshold"),
    #         "ts_flag": inputs.get("ts_flag"),
    #     }
    #
    #     missing = [key for key, value in required_values.items() if not value]
    #
    #     if missing:
    #         return "DSC/PDS选点缺少参数：" + ", ".join(missing)
    #
    #     return self._executor().run_dsc_pds_workflow(
    #         master_date=str(inputs["master_date"]),
    #         ts_dir=str(ts_dir),
    #         diff_shape_dir=inputs["diff_dir"],
    #         phase_opt_mat=str(phase_opt_mat),
    #         matlab_work_dir=inputs["matlab_work_dir"],
    #         matlab_func_dir=inputs["matlab_func_dir"],
    #         fit_threshold=str(inputs["fit_threshold"]),
    #         rg_patches=str(inputs.get("rg_patches", "1")),
    #         az_patches=str(inputs.get("az_patches", "1")),
    #         rg_overlap=str(inputs.get("rg_overlap", "50")),
    #         az_overlap=str(inputs.get("az_overlap", "50")),
    #         ts_flag=str(inputs.get("ts_flag", "1")),
    #         matlab_command=str(inputs.get("matlab_command", "matlab")),
    #         mt_prep_gamma_addds_command=mt_prep_gamma_addds_command,
    #     )

    def run_point_selection_real(self) -> str:
        inputs = self._inputs()
        method = str(inputs.get("point_selection_method", "mt_prep_gamma")).lower()

        if method in {"mt_prep_gamma", "psc", "ps"}:
            return self.run_mt_prep_gamma_real()

        if method in {"dsc_select", "dsc"}:
            return self.run_dsc_select_real()

        if method in {"dsc_pds", "pds", "ds"}:
            return self.run_dsc_pds_workflow_real()

        return (
            f"未知选点方法：{method}\n"
            "可选：mt_prep_gamma、dsc_select、dsc_pds"
        )

    def run_dsc_select_real(self) -> str:
        inputs = self._inputs()

        phase_opt_output_name = str(inputs.get("phase_opt_output_name", "phase_opt"))
        phase_opt_mat = (
                Path(inputs["phase_opt_output_dir"]) / f"{phase_opt_output_name}.mat"
        )
        ts_dir = Path(inputs["phase_opt_output_dir"]) / "TS"

        required_values = {
            "phase_opt_output_dir": inputs.get("phase_opt_output_dir"),
            "diff_dir": inputs.get("diff_dir"),
            "matlab_work_dir": inputs.get("matlab_work_dir"),
            "matlab_func_dir": inputs.get("matlab_func_dir"),
            "fit_threshold": inputs.get("fit_threshold"),
        }

        missing = [key for key, value in required_values.items() if not value]

        if missing:
            return "DSC_Select 缺少参数：" + ", ".join(missing)

        return self._executor().run_dsc_select_matlab(
            ts_dir=str(ts_dir),
            diff_shape_dir=inputs["diff_dir"],
            phase_opt_mat=str(phase_opt_mat),
            matlab_work_dir=inputs["matlab_work_dir"],
            matlab_func_dir=inputs["matlab_func_dir"],
            fit_threshold=str(inputs["fit_threshold"]),
            rg_patches=str(inputs.get("rg_patches", "1")),
            az_patches=str(inputs.get("az_patches", "1")),
            rg_overlap=str(inputs.get("rg_overlap", "50")),
            az_overlap=str(inputs.get("az_overlap", "50")),
            matlab_command=str(inputs.get("matlab_command", "matlab")),
        )

    def run_dsc_pds_workflow_real(self) -> str:
        inputs = self._inputs()

        phase_opt_output_name = str(inputs.get("phase_opt_output_name", "phase_opt"))
        phase_opt_mat = (
                Path(inputs["phase_opt_output_dir"]) / f"{phase_opt_output_name}.mat"
        )
        ts_dir = Path(inputs["phase_opt_output_dir"]) / "TS"

        mt_prep_gamma_addds_command = str(
            inputs.get("mt_prep_gamma_addds_command", "mt_prep_gamma_addDS")
        )

        required_values = {
            "master_date": inputs.get("master_date"),
            "phase_opt_output_dir": inputs.get("phase_opt_output_dir"),
            "diff_dir": inputs.get("diff_dir"),
            "matlab_work_dir": inputs.get("matlab_work_dir"),
            "matlab_func_dir": inputs.get("matlab_func_dir"),
            "fit_threshold": inputs.get("fit_threshold"),
            "ts_flag": inputs.get("ts_flag"),
        }

        missing = [key for key, value in required_values.items() if not value]

        if missing:
            return "DSC/PDS选点缺少参数：" + ", ".join(missing)

        return self._executor().run_dsc_pds_workflow(
            master_date=str(inputs["master_date"]),
            ts_dir=str(ts_dir),
            diff_shape_dir=inputs["diff_dir"],
            phase_opt_mat=str(phase_opt_mat),
            matlab_work_dir=inputs["matlab_work_dir"],
            matlab_func_dir=inputs["matlab_func_dir"],
            fit_threshold=str(inputs["fit_threshold"]),
            rg_patches=str(inputs.get("rg_patches", "1")),
            az_patches=str(inputs.get("az_patches", "1")),
            rg_overlap=str(inputs.get("rg_overlap", "50")),
            az_overlap=str(inputs.get("az_overlap", "50")),
            ts_flag=str(inputs.get("ts_flag", "1")),
            matlab_command=str(inputs.get("matlab_command", "matlab")),
            mt_prep_gamma_addds_command=mt_prep_gamma_addds_command,
        )

    def run_point_selection_real(self) -> str:
        inputs = self._inputs()
        method = str(inputs.get("point_selection_method", "mt_prep_gamma")).lower()

        if method in {"mt_prep_gamma", "psc", "ps"}:
            return self.run_mt_prep_gamma_real()

        if method in {"dsc_select", "dsc"}:
            return self.run_dsc_select_real()

        if method in {"dsc_pds", "pds", "ds"}:
            return self.run_dsc_pds_workflow_real()

        return (
            f"未知选点方法：{method}\n"
            "可选：mt_prep_gamma、dsc_select、dsc_pds"
        )
    ################stamps处理##################
    def run_stamps_processing_real(self) -> str:
        inputs = self._inputs()

        phase_opt_output_dir = inputs.get("phase_opt_output_dir")
        if not phase_opt_output_dir:
            return "StaMPS 处理缺少参数：phase_opt_output_dir"

        stamps_mode = str(inputs.get("stamps_mode", "sbas")).lower()
        matlab_command = str(inputs.get("matlab_command", "matlab"))

        # 允许配置文件手动指定，优先级最高
        stamps_work_dir = inputs.get("stamps_work_dir")

        if not stamps_work_dir:
            ts_dir = Path(phase_opt_output_dir) / "TS"

            if stamps_mode == "sbas":
                stamps_work_dir = ts_dir / "PS-TS" / "PATCH_1"
            elif stamps_mode in {"ps", "ds"}:
                stamps_work_dir = ts_dir / "PDS-TS" / "PATCH_1"
            else:
                return "stamps_mode 参数错误：只能是 ps / sbas / ds"

        return self._executor().run_stamps_processing(
            stamps_work_dir=str(stamps_work_dir),
            stamps_mode=stamps_mode,
            matlab_command=matlab_command,
        )
    #############消息################
    def _notify(self, title: str, content: str) -> str:
        inputs = self._inputs()
        return notify_from_inputs(inputs, title, content)

    def _run_with_notification(
            self,
            step_name: str,
            func,
    ) -> str:
        inputs = self._inputs()
        task_id = inputs.get("task_id", "unknown_task")

        try:
            result = func()
        except Exception as exc:
            notify_from_inputs(
                inputs,
                title=f"SAR Agent 任务失败：{task_id}",
                content=(
                    f"## 任务失败\n\n"
                    f"- 任务ID：`{task_id}`\n"
                    f"- 步骤：`{step_name}`\n"
                    f"- 错误：`{exc}`"
                ),
            )
            raise

        failed_keywords = [
            "失败",
            "执行失败",
            "ERROR",
            "Error",
            "error",
            "Traceback",
        ]

        is_failed = any(keyword in str(result) for keyword in failed_keywords)

        if is_failed:
            notify_title = f"SAR Agent 步骤失败：{task_id}"
            notify_content = (
                f"## 步骤失败\n\n"
                f"- 任务ID：`{task_id}`\n"
                f"- 步骤：`{step_name}`\n\n"
                f"### 返回摘要\n\n"
                f"```text\n{str(result)[-3000:]}\n```"
            )
        else:
            notify_title = f"SAR Agent 步骤完成：{task_id}"
            notify_content = (
                f"## 步骤完成\n\n"
                f"- 任务ID：`{task_id}`\n"
                f"- 步骤：`{step_name}`\n\n"
                f"### 返回摘要\n\n"
                f"```text\n{str(result)[-2000:]}\n```"
            )

        notify_result = notify_from_inputs(
            inputs,
            title=notify_title,
            content=notify_content,
        )

        return f"{result}\n\n---\n\n通知状态：{notify_result}"
