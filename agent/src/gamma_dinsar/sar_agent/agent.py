from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import tool

from tools import AgentTools

SYSTEM_PROMPT = """
你是 Sentinel-1 InSAR 自动处理 Agent。

你的职责：
1. 通过对话收集任务参数；
2. 读取 YAML 配置文件；
3. 根据用户要求调用已注册工具执行固定处理步骤；
4. 解释工具返回的真实结果。

重要规则：
- 你只能调用已注册工具执行处理，不能自己编写或自由生成 shell / MATLAB / GAMMA 命令。
- 如果用户说“根据配置文件执行/进行/处理/运行 某一步”，你必须先调用 load_task_config 读取配置文件，然后调用对应处理工具。
- 不要只读取配置并总结；除非用户明确说“只查看配置”或“只总结配置”。
- 如果用户已经明确指定步骤，不要反问“要执行哪一步”。
- 工具返回失败时，只能基于工具返回的 stdout/stderr 分析，不要编造原因。
- 不要把未执行的步骤说成已完成。

步骤和工具映射：
- 解压 / unzip / 解压ZIP -> run_unzip_s1_real
- 生成SLC / SLC提取 -> run_generate_slc_real
- 提取burst / burst提取 -> run_extract_burst_real
- 主影像地理编码 / 地理编码 -> run_slc_geo_real
- 配准 / coregistration -> run_slc_coreg_multi_real
- 裁剪 / SLC_copy / 裁剪RSLC -> run_slc_copy_crop_all_real
- 生成RSLC_tab -> write_rslc_tab_from_list_real
- 生成itab / 基线文件 / base_calc -> run_base_calc_itab_real
- 生成RMLI / mk_mli_all -> run_mk_mli_all_real
- 生成差分干涉图 / mk_diff_2d -> run_diff_workflow_real
- 同质像元 / SHP选取 -> run_select_shp_matlab_real
- 相位优化 / EVD / EMI -> run_phase_optimization_workflow_real
- 文件组织 / 构建TS / file_construct -> run_file_construct_real

执行策略：
- 用户说“根据配置文件 <path> 进行文件组织”，执行：
  1. load_task_config(config_path=<path>)
  2. run_file_construct_real()
- 用户说“根据配置文件 <path> 进行相位优化”，执行：
  1. load_task_config(config_path=<path>)
  2. run_phase_optimization_workflow_real()
- 用户说“根据配置文件 <path> 进行同质像元提取”，执行：
  1. load_task_config(config_path=<path>)
  2. run_select_shp_matlab_real()
- 如果缺少参数，由工具返回缺失项后再向用户询问。
"""


def build_tools(agent_tools: AgentTools):
    @tool
    def update_task_info(
        task_id: str | None = None,
        raw_zip_dir: str | None = None,
        task_root: str | None = None,
        work_dir: str | None = None,
        list_file: str | None = None,
        satellite: str | None = None,
        satellite_code: str | None = None,
        polarization: str | None = None,
        polarization_code: str | None = None,
        swath: str | None = None,
        swath_code: str | None = None,
        opod_dir: str | None = None,
        pod_dir: str | None = None,
        dem_file: str | None = None,
        master_date: str | None = None,
        env_scripts: list[str] | None = None,
        matlab_func_dir: str | None = None,
        matlab_command: str | None = None,
        crop_roff: int | None = None,
        crop_nr: int | None = None,
        crop_loff: int | None = None,
        crop_nl: int | None = None,
        bn_start1: int | None = None,
        bn_end1: int | None = None,
        bn_start2: int | str | None = None,
        bn_end2: int | str | None = None,
        bn_start3: int | str | None = None,
        bn_end3: int | str | None = None,
        enable_crop: bool | None = None,
        diff_method: str | None = None,
        shp_method: str | None = None,
        phase_opt_method: str | None = None,
        point_selection_method: str | None = None,
        stamps_mode: str | None = None,
        range_looks: int | str | None = None,
        azimuth_looks: int | str | None = None,
        lat_ovr: int | str | None = None,
        lon_ovr: int | str | None = None,
        rlks: int | str | None = None,
        azlks: int | str | None = None,
        bperp_max: int | str | None = None,
        delta_t_max: int | str | None = None,
        delta_n_max: int | str | None = None,
        fit_threshold: float | str | None = None,
        alpha: float | str | None = None,
        psc_da_thresh: float | str | None = None,
        rg_patches: int | str | None = None,
        az_patches: int | str | None = None,
    ) -> str:
        """更新用户提供的S1预处理任务信息。"""
        kwargs: dict[str, Any] = {
            "task_id": task_id,
            "raw_zip_dir": raw_zip_dir,
            "task_root": task_root,
            "work_dir": work_dir,
            "list_file": list_file,
            "satellite": satellite,
            "satellite_code": satellite_code,
            "polarization": polarization,
            "polarization_code": polarization_code,
            "swath": swath,
            "swath_code": swath_code,
            "opod_dir": opod_dir,
            "pod_dir": pod_dir,
            "dem_file": dem_file,
            "master_date": master_date,
            "env_scripts": env_scripts,
            "matlab_func_dir": matlab_func_dir,
            "matlab_command": matlab_command,
            "crop_roff": crop_roff,
            "crop_nr": crop_nr,
            "crop_loff": crop_loff,
            "crop_nl": crop_nl,
            "bn_start1": bn_start1,
            "bn_end1": bn_end1,
            "bn_start2": bn_start2,
            "bn_end2": bn_end2,
            "bn_start3": bn_start3,
            "bn_end3": bn_end3,
            "enable_crop": enable_crop,
            "diff_method": diff_method,
            "shp_method": shp_method,
            "phase_opt_method": phase_opt_method,
            "point_selection_method": point_selection_method,
            "stamps_mode": stamps_mode,
            "range_looks": range_looks,
            "azimuth_looks": azimuth_looks,
            "lat_ovr": lat_ovr,
            "lon_ovr": lon_ovr,
            "rlks": rlks,
            "azlks": azlks,
            "bperp_max": bperp_max,
            "delta_t_max": delta_t_max,
            "delta_n_max": delta_n_max,
            "fit_threshold": fit_threshold,
            "alpha": alpha,
            "psc_da_thresh": psc_da_thresh,
            "rg_patches": rg_patches,
            "az_patches": az_patches,
        }
        clean = {key: value for key, value in kwargs.items() if value is not None}
        return agent_tools.update_task_info(**clean)

    # @tool
    # def validate_task_info() -> str:
    #     """检查当前任务参数是否完整。"""
    #     return agent_tools.validate_task_info()

    @tool
    def get_task_status() -> str:
        """查看当前任务状态。"""
        return agent_tools.get_task_status()

    @tool
    def get_default_parameters() -> str:
        """查看当前代码默认参数；用户不修改时会使用这些默认值。"""
        return agent_tools.get_default_parameters()

    @tool
    def get_effective_task_parameters() -> str:
        """查看当前任务最终参数，并标明每个字段来自用户覆盖、自动推导还是代码默认。"""
        return agent_tools.get_effective_task_parameters()

    @tool
    def write_yaml_config(config_path: str) -> str:
        """将当前任务输入写入YAML配置文件。"""
        return agent_tools.write_yaml_config(config_path)
    @tool
    def run_unzip_s1_real():
        "执行文件解压"
        return agent_tools.run_unzip_s1_real()

    ##############提取slc方法###################
    @tool
    def run_generate_slc_real() -> str:
        """真实执行S1_SLC_Normal生成SLC。需要slc_dir、satellite_code、polarization_code、swath_code。"""
        return agent_tools.run_generate_slc_real()
    ############读取配置文件###################
    @tool
    def load_task_config(config_path: str) -> str:
        """读取YAML配置文件，并将其中的任务参数写入当前任务状态。"""
        return agent_tools.load_task_config(config_path)
    ##################提取brust#################
    @tool
    def run_extract_burst_real() -> str:
        """真实执行 S1_SLC_Copy_Multi 提取burst。参数从当前任务状态读取，不需要再次传参。"""
        return agent_tools.run_extract_burst_real()
    ####################跳步骤###################
    # @tool
    # def run_preprocessing_until_burst() -> str:
    #     """按配置执行到burst提取阶段。可通过skip_unzip、skip_generate_slc、skip_extract_burst跳过已完成步骤。"""
    #     return agent_tools.run_preprocessing_until_burst()
    #
    ######################地理编码#####################
    @tool
    def run_slc_geo_real()-> str:
        "执行地理编码"
        return agent_tools.run_slc_geo_real()
    ####################影像配准##################
    @tool
    def run_slc_coreg_multi_real() -> str:
        """执行 S1_SLC_COREG_Multi 影像配准。参数从当前任务配置中读取。"""
        return agent_tools.run_slc_coreg_multi_real()
    #################影像裁剪##################
    @tool
    def run_slc_copy_crop_all_real() -> str:
        """使用 run_all 批量执行 SLC_copy 影像裁剪。参数从当前任务配置中读取。"""
        return agent_tools.run_slc_copy_crop_all_real()

    @tool
    def write_rslc_tab_from_list_real() -> str:
        """根据 list_file 和裁剪后的 RSLC 目录结构生成 RSLC_tab。适用于 CROP/$1/$1.rslc 这种旧结构。"""
        return agent_tools.write_rslc_tab_from_list_real()

    @tool
    def run_base_calc_itab_real() -> str:
        """执行 base_calc，生成基线文件 bperp_file 和干涉对表 itab。参数从当前任务配置中读取。"""
        return agent_tools.run_base_calc_itab_real()

    @tool
    def run_mk_mli_all_real() -> str:
        """执行 mk_mli_all，生成 RMLI 强度文件。参数从当前任务配置中读取。"""
        return agent_tools.run_mk_mli_all_real()

    @tool
    def run_diff_workflow_real() -> str:
        """执行 2.4 差分干涉图生成流程：先重新地理编码裁剪后的干涉主影像，再根据 diff_method 选择差分干涉方法。"""
        return agent_tools.run_diff_workflow_real()

    @tool
    def run_select_shp_matlab_real() -> str:
        """
        调用固定 MATLAB 脚本进行同质像元 SHP 选取。

        该工具不会让大模型自由生成 MATLAB 命令，只会根据配置文件中的
        RMLI目录、RMLI参数文件、窗口大小、显著性水平和方法类型生成固定脚本。
        """
        return agent_tools.run_select_shp_matlab_real()

    @tool
    def run_phase_optimization_workflow_real() -> str:
        """
        执行 2.6 相位优化完整流程。

        自动从 DIFF 目录扫描 *.diff_par，读取干涉图尺寸；
        调用固定 MATLAB 脚本执行 EVD/EMI 相位优化；
        输出 fit.mat 和 Goodness_fit 图；
        默认继续生成优化后的差分干涉图。
        """
        return agent_tools.run_phase_optimization_workflow_real()

    @tool
    def run_file_construct_real() -> str:
        """
        调用 file_construct 组织 StaMPS / 时序 InSAR 后续处理所需文件。

        参数来自配置文件，不允许大模型自由拼接命令。
        """
        return agent_tools.run_file_construct_real()

    @tool
    def run_mt_prep_gamma_real() -> str:
        """
        调用 mt_prep_gamma 提取 PSC 点。

        PS模式使用 da_thresh 默认 0.4；
        SBAS模式使用 da_thresh 默认 0.6；
        master_date、TS目录、ts_flag 来自配置文件。
        """
        return agent_tools.run_mt_prep_gamma_real()

    @tool
    def run_dsc_pds_workflow_real() -> str:
        """
        执行 DSC/PDS 选点流程。

        包括 DSC_Select、PDS_Merge、mt_prep_gamma_addDS。
        该流程作为 mt_prep_gamma PSC 选点的替代路线。
        """
        return agent_tools.run_dsc_pds_workflow_real()

    @tool
    def run_point_selection_real() -> str:
        """
        根据配置文件中的 point_selection_method 执行选点。

        point_selection_method=mt_prep_gamma 时执行 mt_prep_gamma；
        point_selection_method=dsc_pds 时执行 DSC_Select + PDS_Merge + mt_prep_gamma_addDS。
        """
        return agent_tools.run_point_selection_real()

    @tool
    def run_dsc_select_real() -> str:
        """
        单独执行 DSC_Select，根据相位优化生成的 goodness_fit 提取 DSC 点。
        """
        return agent_tools.run_dsc_select_real()

    @tool
    def run_stamps_processing_real() -> str:
        """
        执行 StaMPS 处理。

        仅支持三种固定模式：ps、sbas、ds。
        根据 stamps_mode 自动设置参数，并固定运行 stamps(1,7)。
        不执行 ps_plot 出图。
        """
        return agent_tools.run_stamps_processing_real()


    @tool
    def run_stamps_processing_real() -> str:
        """根据配置文件执行 StaMPS 处理。"""
        return agent_tools.run_stamps_processing_real()


    return [
        update_task_info,
        get_task_status,
        get_default_parameters,
        get_effective_task_parameters,
        write_yaml_config,
        run_unzip_s1_real,
        run_generate_slc_real,
        load_task_config,
        run_extract_burst_real,
        run_slc_geo_real,
        run_slc_coreg_multi_real,
        run_slc_copy_crop_all_real,
        write_rslc_tab_from_list_real,
        run_base_calc_itab_real,
        run_mk_mli_all_real,
        run_diff_workflow_real,
        run_select_shp_matlab_real,
        run_phase_optimization_workflow_real,
        run_file_construct_real,
        run_mt_prep_gamma_real,
        run_dsc_pds_workflow_real,
        run_point_selection_real,
        run_dsc_select_real,
        run_stamps_processing_real,

        # run_preprocessing_until_burst,
    ]


def create_dinsar_agent(llm: BaseChatModel, agent_tools: AgentTools | None = None):
    if agent_tools is None:
        agent_tools = AgentTools()

    return create_agent(
        model=llm,
        tools=build_tools(agent_tools),
        system_prompt=SYSTEM_PROMPT,
    )
