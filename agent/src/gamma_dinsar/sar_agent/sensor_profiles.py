from __future__ import annotations

from dataclasses import dataclass


SHARED_TIME_SERIES_STEPS = (
    "write_rslc_tab",
    "base_calc",
    "mk_mli_all",
    "diff_workflow",
    "select_shp",
    "phase_optimization",
    "file_construct",
    "point_selection",
    "stamps_processing",
)


@dataclass(frozen=True)
class SensorProfile:
    key: str
    title: str
    short_title: str
    raw_input_key: str
    raw_input_label: str
    raw_input_description: str
    workflow_steps: tuple[str, ...]
    preprocessing_wrapper: str | None
    preprocessing_commands: tuple[str, ...]
    source_scripts: tuple[str, ...]
    polarization_options: tuple[str, ...] = ()
    polarization_codes: tuple[tuple[str, str], ...] = ()
    needs_orbit_dir: bool = False
    orbit_wrapper: str | None = None
    geo_wrapper: str | None = None
    geo_uses_oversampling: bool = True
    coregistration_options: tuple[str, ...] = ()
    default_coregistration_method: str | None = None
    note: str = ""

    def polarization_code(self, value: str) -> str | None:
        normalized = str(value or "").strip().upper()
        return dict(self.polarization_codes).get(normalized)


S1_STEPS = (
    "unzip_s1",
    "generate_slc",
    "extract_burst",
    "slc_geo",
    "coregistration",
    "crop_rslc",
    *SHARED_TIME_SERIES_STEPS,
)

STANDARD_STEPS = (
    "prepare_sensor_raw",
    "generate_slc",
    "apply_orbit",
    "slc_geo",
    "coregistration",
    "stage_rslc",
    *SHARED_TIME_SERIES_STEPS,
)

STANDARD_STEPS_WITHOUT_ORBIT = tuple(step for step in STANDARD_STEPS if step != "apply_orbit")


SENSOR_PROFILES: tuple[SensorProfile, ...] = (
    SensorProfile(
        key="sentinel_1",
        title="Sentinel-1 TOPS (S1A / S1B)",
        short_title="Sentinel-1",
        raw_input_key="raw_zip_dir",
        raw_input_label="Sentinel-1 ZIP 路径",
        raw_input_description="Sentinel-1 SLC ZIP 文件或包含 ZIP 文件的目录。",
        workflow_steps=S1_STEPS,
        preprocessing_wrapper="S1_SLC_Normal",
        preprocessing_commands=("par_S1_SLC", "SLC_copy_S1_TOPS", "SLC_mosaic_S1_TOPS", "rasSLC"),
        source_scripts=(
            "Preprocessing/S1/modified/S1_SLC_Normal",
            "Preprocessing/S1/modified/S1_SLC_Copy_Multi",
        ),
        polarization_options=("VV", "VH"),
        polarization_codes=(("VV", "0"), ("VH", "1")),
        coregistration_options=("tops_spectral_diversity",),
        default_coregistration_method="tops_spectral_diversity",
        note="TOPS 数据需要 Swath 与 Burst 选择，不能套用条带模式的配准参数。",
    ),
    SensorProfile(
        key="alos_palsar",
        title="ALOS PALSAR Level 1.1",
        short_title="ALOS PALSAR",
        raw_input_key="raw_data_dir",
        raw_input_label="已解压 ALOS PALSAR 原始数据目录",
        raw_input_description="包含每景 Level 1.1 原始数据目录；任务会先复制到任务目录再执行封装脚本。",
        workflow_steps=STANDARD_STEPS_WITHOUT_ORBIT,
        preprocessing_wrapper="ALOS_SLC_Normal",
        preprocessing_commands=("par_EORC_PALSAR", "radcal_SLC", "rasSLC"),
        source_scripts=(
            "Preprocessing/ALOS/ALOS_SLC_Normal",
            "Preprocessing/ALOS/ALOS_SLC_GEO",
            "Preprocessing/ALOS/ALOS_SLC_COREG",
        ),
        polarization_options=("HH", "HV", "VH", "VV"),
        polarization_codes=(("HH", "0"), ("HV", "1"), ("VH", "2"), ("VV", "3")),
        coregistration_options=("cross_correlation", "dem_lookup"),
        default_coregistration_method="cross_correlation",
        geo_wrapper="ALOS_SLC_GEO",
        note="可选择互相关配准或基于 DEM 查找表的配准；后者会要求先完成主影像地理编码。",
    ),
    SensorProfile(
        key="terrasar_x",
        title="TerraSAR-X",
        short_title="TerraSAR-X",
        raw_input_key="raw_data_dir",
        raw_input_label="已解压 TerraSAR-X 原始数据目录",
        raw_input_description="包含每景 TerraSAR-X 产品目录；任务会先复制到任务目录再执行封装脚本。",
        workflow_steps=STANDARD_STEPS_WITHOUT_ORBIT,
        preprocessing_wrapper="TX_SLC_Normal",
        preprocessing_commands=("par_TX_SLC", "rasSLC"),
        source_scripts=(
            "Preprocessing/TX/TX_SLC_Normal",
            "Preprocessing/TX/TX_SLC_GEO",
            "Preprocessing/TX/TX_SLC_COREG",
            "Preprocessing/TX/D-InSAR_TX",
        ),
        polarization_options=("HH", "HV", "VH", "VV"),
        polarization_codes=(("HH", "0"), ("HV", "1"), ("VH", "2"), ("VV", "3")),
        coregistration_options=("cross_correlation",),
        default_coregistration_method="cross_correlation",
        geo_wrapper="TX_SLC_GEO",
        geo_uses_oversampling=False,
    ),
    SensorProfile(
        key="gf3",
        title="GF-3 UFS",
        short_title="GF-3",
        raw_input_key="raw_data_dir",
        raw_input_label="已解压 GF-3 UFS 原始数据目录",
        raw_input_description="包含 TIFF 与 meta.xml 的 GF-3 UFS 产品目录；任务会先复制到任务目录。",
        workflow_steps=STANDARD_STEPS_WITHOUT_ORBIT,
        preprocessing_wrapper="GF3_SLC",
        preprocessing_commands=("par_GF3_SLC", "rasSLC"),
        source_scripts=(
            "Preprocessing/GF3/GF3_SLC",
            "Preprocessing/GF3/GF3_GEO",
            "Preprocessing/GF3/GF3_COREG",
        ),
        coregistration_options=("cross_correlation",),
        default_coregistration_method="cross_correlation",
        geo_wrapper="GF3_GEO",
        note="原有说明明确提示 GF-3 轨道稳定性与入射角差异可能导致参数文件或配准失败，应先检查配准质量。",
    ),
    SensorProfile(
        key="radarsat_2",
        title="RADARSAT-2",
        short_title="RADARSAT-2",
        raw_input_key="raw_data_dir",
        raw_input_label="已解压 RADARSAT-2 原始数据目录",
        raw_input_description="包含 product、lutSigma 与 TIFF 文件的 RADARSAT-2 产品目录；任务会先复制到任务目录。",
        workflow_steps=STANDARD_STEPS_WITHOUT_ORBIT,
        preprocessing_wrapper="RADA2_SLC_Normal",
        preprocessing_commands=("par_RSAT2_SLC", "rasSLC"),
        source_scripts=(
            "Preprocessing/Radasat/RADA2_SLC_Normal",
            "Preprocessing/Radasat/RADA2_SLC_GEO",
            "Preprocessing/Radasat/RADA2_SLC_COREG",
            "Preprocessing/Radasat/D-InSAR_RADA2",
        ),
        polarization_options=("HH", "VV", "VH", "HV"),
        polarization_codes=(("HH", "0"), ("VV", "1"), ("VH", "2"), ("HV", "3")),
        coregistration_options=("dem_lookup",),
        default_coregistration_method="dem_lookup",
        geo_wrapper="RADA2_SLC_GEO",
        geo_uses_oversampling=False,
        note="现有封装仅确认 RADARSAT-2，不适用于 RADARSAT-1。",
    ),
    SensorProfile(
        key="envisat_asar",
        title="ENVISAT ASAR IMS",
        short_title="ENVISAT",
        raw_input_key="raw_data_dir",
        raw_input_label="已解压 ENVISAT ASAR 原始数据目录",
        raw_input_description="包含 ASA_IMS 原始文件的目录；任务会在副本内按日期整理、生成 SLC 并应用精轨。",
        workflow_steps=STANDARD_STEPS,
        preprocessing_wrapper="ENVISAT_SLC",
        preprocessing_commands=("par_ASAR", "rasSLC"),
        source_scripts=(
            "Preprocessing/ENVISAT/ENVISAT_mkdir",
            "Preprocessing/ENVISAT/ENVISAT_SLC",
            "Preprocessing/ENVISAT/ENVISAT_OPOD",
            "Preprocessing/ENVISAT/ENVISAT_GEO",
            "Preprocessing/ENVISAT/ENVISAT_coreg",
        ),
        needs_orbit_dir=True,
        orbit_wrapper="ENVISAT_OPOD",
        geo_wrapper="ENVISAT_GEO",
        coregistration_options=("dem_lookup",),
        default_coregistration_method="dem_lookup",
    ),
    SensorProfile(
        key="ers_ims",
        title="ERS-1 / ERS-2 IMS",
        short_title="ERS-1 / ERS-2",
        raw_input_key="raw_data_dir",
        raw_input_label="已解压 ERS IMS 原始数据目录",
        raw_input_description="包含 SAR_IMS 原始文件的目录；任务会在副本内按日期整理、生成 SLC 并应用精轨。",
        workflow_steps=STANDARD_STEPS,
        preprocessing_wrapper="ERS_SLC",
        preprocessing_commands=("par_ASAR", "rasSLC"),
        source_scripts=(
            "Preprocessing/ERS-IMS/ERS_mkdir",
            "Preprocessing/ERS-IMS/ERS_SLC",
            "Preprocessing/ERS-IMS/ERS_OPOD",
            "Preprocessing/ERS-IMS/ERS_GEO",
            "Preprocessing/ERS-IMS/ERS_COREG_CC",
            "Preprocessing/ERS-IMS/ERS_COREG_DEM",
        ),
        needs_orbit_dir=True,
        orbit_wrapper="ERS_OPOD",
        geo_wrapper="ERS_GEO",
        coregistration_options=("cross_correlation", "dem_lookup"),
        default_coregistration_method="dem_lookup",
    ),
)


PROFILE_BY_KEY = {profile.key: profile for profile in SENSOR_PROFILES}


def get_sensor_profile(value: object | None) -> SensorProfile:
    key = str(value or "sentinel_1").strip().lower()
    if key not in PROFILE_BY_KEY:
        valid_values = ", ".join(PROFILE_BY_KEY)
        raise ValueError(f"不支持的卫星数据类型：{value}。可选值：{valid_values}")
    return PROFILE_BY_KEY[key]


def sensor_profile_payloads() -> list[dict[str, object]]:
    return [
        {
            "key": profile.key,
            "title": profile.title,
            "short_title": profile.short_title,
            "raw_input_key": profile.raw_input_key,
            "raw_input_label": profile.raw_input_label,
            "raw_input_description": profile.raw_input_description,
            "workflow_steps": list(profile.workflow_steps),
            "preprocessing_wrapper": profile.preprocessing_wrapper,
            "preprocessing_commands": list(profile.preprocessing_commands),
            "source_scripts": list(profile.source_scripts),
            "polarization_options": list(profile.polarization_options),
            "needs_orbit_dir": profile.needs_orbit_dir,
            "coregistration_options": list(profile.coregistration_options),
            "default_coregistration_method": profile.default_coregistration_method,
            "note": profile.note,
        }
        for profile in SENSOR_PROFILES
    ]
