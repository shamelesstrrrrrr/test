from src.gamma_dinsar.sar_agent.specs import StageSpec

S1_PREPROCESSING_STAGES = [
    StageSpec(
        name="unzip_s1",
        title="解压S1原始数据文件",
        description="将Sentinel-1 ZIP原始数据解压到SLC目录。",
        required_inputs=["raw_zip_dir", "work_dir", "slc_dir"],
        derived_inputs={"slc_dir": "{work_dir}/SLC"},
        outputs=["SLC"],
        command_template_id="unzip_s1_zip",
    ),
    StageSpec(
        name="generate_slc",
        title="生成SLC数据",
        description="使用S1_SLC_Normal生成SLC数据。",
        required_inputs=["slc_dir", "satellite_code", "polarization_code", "swath_code"],
        optional_inputs={"polarization": "VV", "polarization_code": "0"},
        outputs=["SLC日期目录"],
        command_template_id="s1_slc_normal",
    ),
    StageSpec(
        name="extract_burst",
        title="提取burst区域",
        description=(
            "使用 S1_SLC_Copy_Multi 提取 burst 区域。"
            "该命令支持单 swath 和多 swath。"
            "对于 S1A，burst 编号从图像顶部向底部递增；"
            "对于 S1B，burst 编号从图像底部向顶部递增。"
        ),
        required_inputs=[
            "unzip_slc_dir",
            "slc_dir",
            "burst_dir",
            "polarization_code",
            "swath_code",
            "bn_start1",
            "bn_end1",
        ],
        optional_inputs={
            "bn_start2": "-",
            "bn_end2": "-",
            "bn_start3": "-",
            "bn_end3": "-",
        },
        derived_inputs={
            "unzip_slc_dir": "{slc_dir}",
            "burst_dir": "{work_dir}/SLC_select",
        },
        outputs=["SLC_select"],
        command_template_id="s1_slc_copy_multi",
    ),
    StageSpec(
        name="apply_orbit",
        title="精轨校正",
        description="使用S1_SLC_OPOD进行精轨校正。",
        required_inputs=["s1_slc_dir", "pod_dir", "date_list", "polarization_code", "swath_code"],
        derived_inputs={"s1_slc_dir": "{work_dir}/SLC_select", "date_list": "{work_dir}/SLC_select/list"},
        outputs=["精轨校正后的SLC"],
        command_template_id="s1_slc_opod",
    ),
    StageSpec(
        name="master_geocoding",
        title="主影像地理编码",
        description="使用DEM对主影像进行地理编码。",
        required_inputs=["geo_dir", "slc_file", "dem_file", "range_looks", "azimuth_looks", "lat_ov", "lon_ov"],
        derived_inputs={"geo_dir": "{work_dir}/GEO", "slc_file": "{work_dir}/SLC_select/{master_date}.slc"},
        optional_inputs={"range_looks": 1, "azimuth_looks": 1, "lat_ov": 5, "lon_ov": 5},
        outputs=["GEO", "SAR_DEM"],
        command_template_id="s1_slc_geo",
    ),
    StageSpec(
        name="coregistration",
        title="影像配准",
        description="使用S1_SLC_COREG_Multi进行配准。",
        required_inputs=["slc_dir", "geo_dir", "rslc_dir", "list_file"],
        derived_inputs={"geo_dir": "{work_dir}/GEO", "rslc_dir": "{work_dir}/RSLC", "list_file": "{work_dir}/SLC_select/list"},
        outputs=["RSLC"],
        command_template_id="s1_slc_coreg_multi",
    ),
    StageSpec(
        name="crop_rslc",
        title="影像裁剪",
        description="使用SLC_copy裁剪RSLC。",
        required_inputs=["input_rslc", "input_rslc_par", "output_rslc", "output_rslc_par", "crop_roff", "crop_nr", "crop_loff", "crop_nl"],
        optional_inputs={"data_format": "-", "scale_factor": "-"},
        outputs=["SLC_copy"],
        command_template_id="slc_copy",
    ),
]