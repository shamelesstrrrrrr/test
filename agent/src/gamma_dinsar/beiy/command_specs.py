from src.gamma_dinsar.sar_agent.specs import CommandInputSpec, CommandSpec


SATELLITE_OPTIONS = {
    "S1A": "0",
    "A": "0",
    "0": "0",
    "S1B": "1",
    "B": "1",
    "1": "1",
}

POLARIZATION_OPTIONS = {
    "VV": "0",
    "0": "0",
    "VH": "1",
    "1": "1",
}

SWATH_OPTIONS = {
    "IW1": "1",
    "1": "1",
    "IW2": "2",
    "2": "2",
    "IW3": "3",
    "3": "3",
    "IW1+IW2": "4",
    "4": "4",
    "IW2+IW3": "5",
    "5": "5",
    "IW1+IW2+IW3": "6",
    "6": "6",
}


def normalize_option(value: str, options: dict[str, str], field_name: str) -> str:
    key = value.strip().upper()

    if key not in options:
        valid_values = ", ".join(options.keys())
        raise ValueError(f"{field_name} 输入无效：{value}。可选值：{valid_values}")

    return options[key]


COMMAND_SPECS = {
    "unzip_s1_zip": CommandSpec(
        command_id="unzip_s1_zip",
        command_name="unzip",
        mode="argv",
        verification_status="verified_from_document",
        argv_template=[
            "-d",
            "{unzip_dir}",
            "{raw_zip_dir}/*.ZIP",
        ],
        argv_sequence=[
            CommandInputSpec("raw_zip_dir", "原始 Sentinel-1 ZIP 文件所在目录"),
            CommandInputSpec("unzip_dir", "ZIP 解压输出目录"),
        ],
        notes="流程第 1 步：raw_zip_dir -> unzip_dir。",
    ),
    "s1_slc_normal": CommandSpec(
        command_id="s1_slc_normal",
        command_name="S1_SLC_Normal",
        mode="argv",
        verification_status="needs_user_confirmed_template",
        argv_template=[
            "{unzip_dir}",
            "{slc_dir}",
            "{satellite_code}",
            "{polarization_code}",
            "{swath_code}",
        ],
        argv_sequence=[
            CommandInputSpec("unzip_dir", "解压后的 Sentinel-1 SAFE 数据目录"),
            CommandInputSpec("slc_dir", "SLC 生成输出目录"),
            CommandInputSpec("satellite_code", "卫星编号：S1A=0，S1B=1"),
            CommandInputSpec("polarization_code", "极化编号：VV=0，VH=1"),
            CommandInputSpec("swath_code", "子波束编号：IW1=1，IW2=2，IW3=3，组合=4-6"),
        ],
        notes="流程第 2 步：unzip_dir -> slc_dir。当前按用户确认的命令行参数方式执行。",
    ),
    "s1_slc_copy_multi": CommandSpec(
        command_id="s1_slc_copy_multi",
        command_name="S1_SLC_Copy_Multi",
        mode="argv",
        verification_status="needs_user_confirmed_template",
        argv_template=[
            "{slc_dir}",
            "{burst_dir}",
            "{polarization_code}",
            "{swath_code}",
            "{bn_start1}",
            "{bn_end1}",
            "{bn_start2}",
            "{bn_end2}",
            "{bn_start3}",
            "{bn_end3}",
        ],
        argv_sequence=[
            CommandInputSpec("slc_dir", "S1_SLC_Normal 生成的 SLC 目录"),
            CommandInputSpec("burst_dir", "burst 提取输出目录"),
            CommandInputSpec("polarization_code", "极化编号：VV=0，VH=1"),
            CommandInputSpec("swath_code", "子波束编号：IW1=1，IW2=2，IW3=3，组合=4-6"),
            CommandInputSpec("bn_start1", "第一个 swath 的起始 burst 编号"),
            CommandInputSpec("bn_end1", "第一个 swath 的结束 burst 编号"),
            CommandInputSpec("bn_start2", "第二个 swath 的起始 burst 编号；不用时填 '-'", required=False, default="-"),
            CommandInputSpec("bn_end2", "第二个 swath 的结束 burst 编号；不用时填 '-'", required=False, default="-"),
            CommandInputSpec("bn_start3", "第三个 swath 的起始 burst 编号；不用时填 '-'", required=False, default="-"),
            CommandInputSpec("bn_end3", "第三个 swath 的结束 burst 编号；不用时填 '-'", required=False, default="-"),
        ],
        notes=(
            "流程第 3 步：slc_dir -> burst_dir。"
            "注意：S1A 的 burst 编号从 1 开始，自图像顶部向底部递增；"
            "S1B 的 burst 编号从 1 开始，自图像底部向顶部递增。"
        ),
    ),
}
