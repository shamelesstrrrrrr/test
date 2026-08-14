from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path

from sensor_profiles import get_sensor_profile


BUNDLED_SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
SHP_VARIABLE_BY_METHOD = {
    "tTest": "TSHP",
    "KSTest": "KSSHP",
    "ADTest2": "ADSHP",
    "GLRtest": "GLRSHP",
    "HTCI": "HTCISHP",
}

class LocalCommandExecutor:
    def __init__(self, env_scripts: list[str] | None = None) -> None:
        self.env_scripts = env_scripts or []

    def _has_error_output(self, output: str) -> bool:
        markers = (
            "ERROR:",
            "Traceback",
            "cannot open",
            "cannot input",
            "No such file",
            "没有那个文件或目录",
        )
        return any(marker in output for marker in markers)

    def _build_shell_command(self, command: str) -> str:
        parts = []

        for script in self.env_scripts:
            parts.append(f"source {shlex.quote(script)}")

        parts.append(command)

        return " && ".join(parts)

    def _run_profile_command(
        self,
        command: str,
        *,
        cwd: Path,
        timeout: int = 3600,
        success_title: str,
    ) -> str:
        shell_command = self._build_shell_command(command)
        print(f">>> command={command}", flush=True)
        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        if result.returncode != 0 or self._has_error_output(combined_output):
            return (
                f"{success_title}失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout[-4000:]}\n"
                f"stderr:\n{result.stderr[-4000:]}"
            )
        return (
            f"{success_title}完成。\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )

    def prepare_sensor_raw_data(self, raw_data_dir: str, slc_dir: str) -> str:
        source = Path(raw_data_dir).expanduser()
        destination = Path(slc_dir).expanduser()

        if not source.is_dir():
            return f"已解压原始数据目录不存在或不是目录：{source}"

        try:
            if source.resolve() == destination.resolve():
                return "原始数据目录不能与任务 SLC 目录相同，以免修改用户原始数据。"
        except OSError:
            pass

        if destination.exists() and any(destination.iterdir()):
            return f"任务 SLC 目录已存在内容，未覆盖：{destination}"

        destination.mkdir(parents=True, exist_ok=True)
        copied = 0
        try:
            for item in source.iterdir():
                target = destination / item.name
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
                copied += 1
        except Exception as exc:
            return f"复制原始数据副本失败：{exc}"

        return f"已复制 {copied} 项原始数据到任务 SLC 目录：{destination}"

    def _write_date_list(self, slc_dir: Path, list_file: Path) -> str:
        dates = sorted(
            item.name
            for item in slc_dir.iterdir()
            if item.is_dir() and re.fullmatch(r"\d{8}", item.name)
        )
        if not dates:
            return f"未在 SLC 目录中找到 YYYYMMDD 日期目录：{slc_dir}"
        list_file.parent.mkdir(parents=True, exist_ok=True)
        list_file.write_text("\n".join(dates) + "\n", encoding="utf-8")
        return f"已生成日期列表：{list_file}（{len(dates)} 景）"

    def run_sensor_slc_normal(
        self,
        sensor_profile: str,
        slc_dir: str,
        list_file: str,
        polarization: str = "",
        timeout: int = 3600,
    ) -> str:
        profile = get_sensor_profile(sensor_profile)
        slc_path = Path(slc_dir).expanduser()
        if profile.key == "sentinel_1":
            return "Sentinel-1 不使用通用 SLC 生成入口。"
        if not slc_path.is_dir():
            return f"任务 SLC 目录不存在：{slc_path}"
        if not profile.preprocessing_wrapper:
            return f"{profile.title} 未配置 SLC 封装脚本。"

        commands: list[str] = []
        if profile.key == "envisat_asar":
            commands.append(f"ENVISAT_mkdir {shlex.quote(str(slc_path))}")
        elif profile.key == "ers_ims":
            commands.append(f"ERS_mkdir {shlex.quote(str(slc_path))}")

        args = [profile.preprocessing_wrapper, str(slc_path)]
        if profile.polarization_options:
            code = profile.polarization_code(polarization)
            if code is None:
                options = "/".join(profile.polarization_options)
                return f"{profile.short_title} 的 polarization 无效：{polarization}。可选：{options}"
            args.append(code)
        commands.append(" ".join(shlex.quote(value) for value in args))

        result = self._run_profile_command(
            " && ".join(commands),
            cwd=slc_path,
            timeout=timeout,
            success_title=f"{profile.short_title} SLC 生成",
        )
        if "失败" in result:
            return result
        return result + "\n" + self._write_date_list(slc_path, Path(list_file).expanduser())

    def run_sensor_orbit(
        self,
        sensor_profile: str,
        slc_dir: str,
        orbit_dir: str,
        timeout: int = 3600,
    ) -> str:
        profile = get_sensor_profile(sensor_profile)
        if not profile.needs_orbit_dir or not profile.orbit_wrapper:
            return f"{profile.short_title} 不需要单独执行精密轨道封装步骤。"
        slc_path = Path(slc_dir).expanduser()
        orbit_path = Path(orbit_dir).expanduser()
        if not slc_path.is_dir():
            return f"SLC 目录不存在：{slc_path}"
        if not orbit_path.is_dir():
            return f"精密轨道目录不存在：{orbit_path}"
        command = " ".join(
            shlex.quote(value)
            for value in (profile.orbit_wrapper, str(slc_path), str(orbit_path))
        )
        return self._run_profile_command(
            command,
            cwd=slc_path,
            timeout=timeout,
            success_title=f"{profile.short_title} 精密轨道校正",
        )

    def run_sensor_slc_geo(
        self,
        sensor_profile: str,
        geo_dir: str,
        slc_file: str,
        dem_file: str,
        range_looks: str,
        azimuth_looks: str,
        lat_ovr: str,
        lon_ovr: str,
        timeout: int = 3600,
    ) -> str:
        profile = get_sensor_profile(sensor_profile)
        geo_path = Path(geo_dir).expanduser()
        slc_path = Path(slc_file).expanduser()
        dem_path = Path(dem_file).expanduser()
        if not profile.geo_wrapper:
            return f"{profile.short_title} 未配置地理编码封装脚本。"
        if not slc_path.is_file():
            return f"待地理编码的 SLC 文件不存在：{slc_path}"
        if not dem_path.is_file():
            return f"DEM 文件不存在：{dem_path}"
        geo_path.mkdir(parents=True, exist_ok=True)

        args = [
            profile.geo_wrapper,
            str(geo_path),
            str(slc_path),
            str(dem_path),
            str(range_looks),
            str(azimuth_looks),
        ]
        if profile.geo_uses_oversampling:
            args.extend((str(lat_ovr), str(lon_ovr)))
        command = " ".join(shlex.quote(value) for value in args)
        return self._run_profile_command(
            command,
            cwd=geo_path,
            timeout=timeout,
            success_title=f"{profile.short_title} SLC 地理编码",
        )

    def run_sensor_coregistration(
        self,
        sensor_profile: str,
        slc_dir: str,
        list_file: str,
        geo_dir: str,
        coreg_dir: str,
        master_date: str,
        polarization: str = "",
        method: str = "",
        timeout: int = 7200,
    ) -> str:
        profile = get_sensor_profile(sensor_profile)
        slc_path = Path(slc_dir).expanduser()
        list_path = Path(list_file).expanduser()
        geo_path = Path(geo_dir).expanduser()
        coreg_path = Path(coreg_dir).expanduser()
        selected_method = method or profile.default_coregistration_method or ""

        if not slc_path.is_dir() or not list_path.is_file():
            return f"影像配准前置数据不完整：slc_dir={slc_path}，list_file={list_path}"
        coreg_path.mkdir(parents=True, exist_ok=True)

        if profile.key == "alos_palsar":
            if selected_method == "dem_lookup":
                args = ("ALOS_SLC_COREG_DEM", str(slc_path), str(geo_path), str(list_path), str(coreg_path))
            else:
                args = ("ALOS_SLC_COREG", str(slc_path), str(list_path), str(coreg_path), str(geo_path))
        elif profile.key == "terrasar_x":
            ref = slc_path / str(master_date) / f"{master_date}.slc"
            args = ("TX_SLC_COREG", str(slc_path), str(list_path), str(ref), str(coreg_path))
        elif profile.key == "gf3":
            ref = slc_path / str(master_date) / f"{master_date}.slc"
            args = ("GF3_COREG", str(slc_path), str(list_path), str(coreg_path), str(ref))
        elif profile.key == "radarsat_2":
            code = profile.polarization_code(polarization)
            if code is None:
                options = "/".join(profile.polarization_options)
                return f"RADARSAT-2 的 polarization 无效：{polarization}。可选：{options}"
            args = ("RADA2_SLC_COREG", str(slc_path), str(list_path), str(coreg_path), str(geo_path), code)
        elif profile.key == "envisat_asar":
            args = ("ENVISAT_coreg", str(coreg_path), str(geo_path), str(slc_path), str(list_path))
        elif profile.key == "ers_ims":
            if selected_method == "cross_correlation":
                ref = slc_path / str(master_date) / f"{master_date}.slc"
                args = ("ERS_COREG_CC", str(slc_path), str(list_path), str(ref), str(coreg_path))
            else:
                args = ("ERS_COREG_DEM", str(coreg_path), str(geo_path), str(slc_path), str(list_path))
        else:
            return f"{profile.short_title} 未配置通用配准封装调用。"

        command = " ".join(shlex.quote(value) for value in args)
        return self._run_profile_command(
            command,
            cwd=coreg_path,
            timeout=timeout,
            success_title=f"{profile.short_title} 影像配准（{selected_method}）",
        )

    def stage_sensor_rslc(
        self,
        coreg_dir: str,
        list_file: str,
        crop_dir: str,
        timeout: int = 30,
    ) -> str:
        del timeout
        coreg_path = Path(coreg_dir).expanduser()
        list_path = Path(list_file).expanduser()
        stage_path = Path(crop_dir).expanduser()
        if not coreg_path.is_dir() or not list_path.is_file():
            return f"整理 RSLC 前置数据不完整：coreg_dir={coreg_path}，list_file={list_path}"

        dates = [line.strip() for line in list_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not dates:
            return f"日期列表为空：{list_path}"
        if stage_path.exists() and any(stage_path.iterdir()):
            return f"RSLC 整理输出目录已存在内容，未覆盖：{stage_path}"
        stage_path.mkdir(parents=True, exist_ok=True)

        missing: list[str] = []
        for date in dates:
            source_dir = coreg_path / date
            source_slc = source_dir / f"{date}.rslc"
            source_par = source_dir / f"{date}.rslc.par"
            if not source_slc.is_file() or not source_par.is_file():
                missing.extend(str(path) for path in (source_slc, source_par) if not path.is_file())
                continue
            destination_dir = stage_path / date
            destination_dir.mkdir(parents=True, exist_ok=False)
            (destination_dir / source_slc.name).symlink_to(source_slc)
            (destination_dir / source_par.name).symlink_to(source_par)

        if missing:
            return "整理 RSLC 失败，缺少以下配准结果：\n" + "\n".join(missing)
        return f"已将 {len(dates)} 景 RSLC 整理到：{stage_path}"

    def run_unzip_s1(
        self,
        raw_zip_dir: str,
        unzip_dir: str,
        timeout: int = 3600,
    ) -> str:
        raw_path = Path(raw_zip_dir).expanduser()
        unzip_path = Path(unzip_dir).expanduser()

        print(">>> RUN unzip", flush=True)
        print(f">>> raw_zip_dir={raw_path}", flush=True)
        print(f">>> unzip_dir={unzip_path}", flush=True)

        if not raw_path.exists():
            return f"原始 ZIP 路径不存在：{raw_path}"

        if raw_path.is_file():
            if raw_path.suffix.lower() != ".zip":
                return f"输入文件不是 ZIP：{raw_path}"
            zip_files = [raw_path]
        else:
            zip_files = sorted(raw_path.glob("*.ZIP")) + sorted(raw_path.glob("*.zip"))

        if not zip_files:
            return f"未找到 ZIP 文件：{raw_path}"

        unzip_path.mkdir(parents=True, exist_ok=True)

        logs: list[str] = []

        for zip_file in zip_files:
            cmd = ["unzip", "-d", str(unzip_path), str(zip_file)]

            result = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=timeout,
            )

            logs.append(f"$ {' '.join(cmd)}")

            if result.stdout:
                logs.append(result.stdout)

            if result.stderr:
                logs.append(result.stderr)

            if result.returncode != 0:
                return (
                    f"解压失败：{zip_file}\n"
                    f"returncode={result.returncode}\n"
                    f"stdout:\n{result.stdout}\n"
                    f"stderr:\n{result.stderr}"
                )

        return (
            f"解压完成，共处理 {len(zip_files)} 个 ZIP 文件，输出目录：{unzip_path}\n"
            + "\n".join(logs[-10:])
        )

    def run_generate_slc(
            self,
            unzip_dir: str,
            satellite_code: str,
            polarization_code: str,
            swath_code: str,
            timeout: int = 3600,
    ) -> str:
        unzip_path = Path(unzip_dir).expanduser()

        print(">>> RUN S1_SLC_Normal", flush=True)
        print(f">>> unzip_dir={unzip_path}", flush=True)
        print(f">>> satellite_code={satellite_code}", flush=True)
        print(f">>> polarization_code={polarization_code}", flush=True)
        print(f">>> swath_code={swath_code}", flush=True)

        if not unzip_path.exists():
            return f"解压目录不存在：{unzip_path}"

        existing_slc_dirs = self.find_slc_dirs(str(unzip_path))
        if existing_slc_dirs:
            existing = "\n".join(str(path) for path in existing_slc_dirs)
            return (
                "检测到已生成的 SLC 日期目录，已跳过 S1_SLC_Normal，避免重复运行外部重命名脚本。\n"
                f"搜索目录：{unzip_path}\n"
                f"已检测到：\n{existing}\n"
                "如果需要重新生成 SLC，请使用新的 task_root，或手动确认后清理旧的日期 SLC 目录。"
            )

        command = (
            f"S1_SLC_Normal "
            f"{shlex.quote(str(unzip_path))} "
            f"{shlex.quote(str(satellite_code))} "
            f"{shlex.quote(str(polarization_code))} "
            f"{shlex.quote(str(swath_code))}"
        )

        shell_command = self._build_shell_command(command)

        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(unzip_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "生成 SLC 失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            "生成 SLC 命令执行完成。\n"
            f"S1_SLC_Normal 输出目录按当前约定为：{unzip_path}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )

    def run_extract_burst_multi(
            self,
            unzip_dir: str,
            burst_dir: str,
            polarization_code: str,
            swath_code: str,
            bn_start1: str,
            bn_end1: str,
            bn_start2: str = "",
            bn_end2: str = "",
            bn_start3: str = "",
            bn_end3: str = "",
            timeout: int = 3600,
    ) -> str:
        slc_path = Path(unzip_dir).expanduser()
        burst_path = Path(burst_dir).expanduser()
        wrapper_path = BUNDLED_SCRIPTS_DIR / "S1_SLC_Copy_Multi_safe.sh"

        print(">>> RUN S1_SLC_Copy_Multi_safe", flush=True)
        print(f">>> slc_dir={slc_path}", flush=True)
        print(f">>> burst_dir={burst_path}", flush=True)
        print(f">>> polarization_code={polarization_code}", flush=True)
        print(f">>> swath_code={swath_code}", flush=True)
        print(f">>> bn_start1={bn_start1}", flush=True)
        print(f">>> bn_end1={bn_end1}", flush=True)
        print(f">>> bn_start2={bn_start2}", flush=True)
        print(f">>> bn_end2={bn_end2}", flush=True)
        print(f">>> bn_start3={bn_start3}", flush=True)
        print(f">>> bn_end3={bn_end3}", flush=True)

        if not slc_path.exists():
            return f"SLC 目录不存在：{slc_path}"

        if not wrapper_path.is_file():
            return f"Burst 兼容脚本不存在：{wrapper_path}"

        burst_path.mkdir(parents=True, exist_ok=True)

        def has_value(value: str | None) -> bool:
            return value is not None and str(value).strip() not in {"", "-", "None", "none"}

        args = [
            "bash",
            str(wrapper_path),
            str(slc_path),
            str(burst_path),
            str(polarization_code),
            str(swath_code),
            str(bn_start1),
            str(bn_end1),
        ]

        if has_value(bn_start2) or has_value(bn_end2):
            if not (has_value(bn_start2) and has_value(bn_end2)):
                return "第二组 burst 参数不完整：bn_start2 和 bn_end2 必须同时填写，或同时留空。"
            args.extend([str(bn_start2), str(bn_end2)])

        if has_value(bn_start3) or has_value(bn_end3):
            if not (has_value(bn_start3) and has_value(bn_end3)):
                return "第三组 burst 参数不完整：bn_start3 和 bn_end3 必须同时填写，或同时留空。"
            args.extend([str(bn_start3), str(bn_end3)])

        command = " ".join(shlex.quote(arg) for arg in args)
        shell_command = self._build_shell_command(command)

        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(slc_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        combined_output = f"{result.stdout}\n{result.stderr}"
        if result.returncode != 0 or self._has_error_output(combined_output):
            return (
                "提取 burst 失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            "提取 burst 命令执行完成。\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )

    def find_slc_dirs(self, unzip_dir: str) -> list[Path]:
        unzip_path = Path(unzip_dir).expanduser()

        if not unzip_path.exists():
            return []

        slc_dirs: list[Path] = []

        def is_date_slc_dir(path: Path) -> bool:
            return path.is_dir() and re.fullmatch(r"\d{8}", path.name) is not None and (path / "SLC_tab").is_file()

        if is_date_slc_dir(unzip_path):
            slc_dirs.append(unzip_path)

        for child in sorted(unzip_path.iterdir()):
            if is_date_slc_dir(child) and child not in slc_dirs:
                slc_dirs.append(child)

        return slc_dirs

    def run_extract_burst_multi_from_unzip_dir(
            self,
            unzip_dir: str,
            burst_dir: str,
            polarization_code: str,
            swath_code: str,
            bn_start1: str,
            bn_end1: str,
            bn_start2: str = "-",
            bn_end2: str = "-",
            bn_start3: str = "-",
            bn_end3: str = "-",
            timeout: int = 3600,
    ) -> str:
        slc_dirs = self.find_slc_dirs(
            unzip_dir=unzip_dir
        )

        if not slc_dirs:
            return (
                "未找到可用于 burst 提取的 SLC 目录。\n"
                f"搜索目录：{unzip_dir}\n"
                f"swath_code={swath_code}, polarization_code={polarization_code}"
            )

        # The legacy script expects the parent SLC directory, not one date
        # directory at a time. The bundled wrapper filters direct YYYYMMDD
        # children before invoking GAMMA, preventing support/annotation files
        # from being mistaken for acquisition dates.
        return self.run_extract_burst_multi(
            unzip_dir=unzip_dir,
            burst_dir=burst_dir,
            polarization_code=polarization_code,
            swath_code=swath_code,
            bn_start1=bn_start1,
            bn_end1=bn_end1,
            bn_start2=bn_start2,
            bn_end2=bn_end2,
            bn_start3=bn_start3,
            bn_end3=bn_end3,
            timeout=timeout,
        )
    ########################地理编码############
    def run_slc_geo(
            self,
            geo_dir: str,
            slc_file: str,
            dem_file: str,
            range_looks: str = "1",
            azimuth_looks: str = "1",
            lat_ovr: str = "5",
            lon_ovr: str = "5",
            timeout: int = 3600,
    ) -> str:
        geo_path = Path(geo_dir).expanduser()
        slc_path = Path(slc_file).expanduser()
        dem_path = Path(dem_file).expanduser()

        print(">>> RUN S1_SLC_GEO", flush=True)
        print(f">>> geo_dir={geo_path}", flush=True)
        print(f">>> slc_file={slc_path}", flush=True)
        print(f">>> dem_file={dem_path}", flush=True)
        print(f">>> range_looks={range_looks}", flush=True)
        print(f">>> azimuth_looks={azimuth_looks}", flush=True)
        print(f">>> lat_ovr={lat_ovr}", flush=True)
        print(f">>> lon_ovr={lon_ovr}", flush=True)

        if not slc_path.is_file():
            return f"待地理编码的 SLC 文件不存在：{slc_path}"

        if not dem_path.is_file():
            return f"DEM 文件不存在：{dem_path}"

        output_path = geo_path / slc_path.stem
        if output_path.exists():
            return (
                "SLC 地理编码未启动：目标输出目录已存在，可能包含此前的完整结果或"
                "失败残留。为避免混用旧文件，本次任务已停止。\n"
                f"已存在：{output_path}\n"
                "请确认目录内容后，手动移走该目录，或在配置中使用新的 geo_dir。"
            )

        geo_path.mkdir(parents=True, exist_ok=True)

        args = [
            "S1_SLC_GEO",
            str(geo_path),
            str(slc_path),
            str(dem_path),
            str(range_looks),
            str(azimuth_looks),
            str(lat_ovr),
            str(lon_ovr),
        ]

        command = " ".join(shlex.quote(arg) for arg in args)
        shell_command = self._build_shell_command(command)

        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(geo_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        combined_output = f"{result.stdout}\n{result.stderr}"
        if result.returncode != 0 or self._has_error_output(combined_output):
            return (
                "SLC 地理编码失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            "SLC 地理编码命令执行完成。\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )
    ###################影像配准#################
    def run_slc_coreg_multi(
            self,
            burst_dir: str,
            geo_dir: str,
            list_file: str,
            polarization: str,
            swath: str,
            coreg_dir: str,
            timeout: int = 3600,
    ) -> str:
        burst_dir = Path(burst_dir).expanduser()
        geo_path = Path(geo_dir).expanduser()
        list_path = Path(list_file).expanduser()
        coreg_path = Path(coreg_dir).expanduser()

        print(">>> RUN S1_SLC_COREG_Multi", flush=True)
        print(f">>> burst_dir={burst_dir}", flush=True)
        print(f">>> geo_dir={geo_path}", flush=True)
        print(f">>> list_file={list_path}", flush=True)
        print(f">>> polarization={polarization}", flush=True)
        print(f">>> swath={swath}", flush=True)
        print(f">>> coreg_dir={coreg_path}", flush=True)

        if not burst_dir.exists():
            return f"待配准 SLC_select 文件夹不存在：{burst_dir}"

        if not geo_path.exists():
            return f"GEO 文件夹不存在：{geo_path}"

        if not list_path.is_file():
            return f"list 文件不存在：{list_path}"

        coreg_path.mkdir(parents=True, exist_ok=True)

        # S1_coreg_TOPS invokes ScanSAR_coreg.py through the Python resolved
        # after the configured environment scripts have been sourced.
        python_check = (
            "import sys; import distutils; import matplotlib; import numpy; "
            "from scipy.constants import speed_of_light; "
            "print(f'python={sys.executable} version={sys.version.split()[0]}'); "
            "print(f'matplotlib={matplotlib.__version__}'); "
            "print(f'speed_of_light={speed_of_light}')"
        )
        preflight_command = self._build_shell_command(
            f"python -c {shlex.quote(python_check)}"
        )
        preflight = subprocess.run(
            ["bash", "-lc", preflight_command],
            cwd=str(coreg_path),
            text=True,
            capture_output=True,
            timeout=min(timeout, 60),
        )
        if preflight.returncode != 0:
            return (
                "影像配准环境检查失败：GAMMA 的 ScanSAR_coreg.py 需要当前 Python "
                "环境能够导入 distutils、numpy、matplotlib 和 scipy。\n"
                f"stdout:\n{preflight.stdout}\n"
                f"stderr:\n{preflight.stderr}\n"
                "请在 source 与任务相同的 env_scripts 后，运行一次环境初始化脚本：\n"
                f"bash {BUNDLED_SCRIPTS_DIR / 'setup_gamma_python_env.sh'}"
            )

        existing_outputs = [str(path) for path in sorted(coreg_path.iterdir())]
        if existing_outputs:
            return (
                "影像配准未启动：检测到 coreg_dir 不是空目录，可能包含此前的完整"
                "结果或失败残留。为避免覆盖或混入旧文件，本次任务已停止。\n"
                "已存在：\n"
                + "\n".join(existing_outputs)
                + "\n请在确认这些文件仅为失败残留后，手动移走整个 coreg_dir 的内容，"
                "或在配置中使用新的空 coreg_dir。"
            )

        args = [
            "S1_SLC_COREG_Multi",
            str(burst_dir),
            str(geo_path),
            str(list_path),
            str(polarization),
            str(swath),
            str(coreg_path),
        ]

        command = " ".join(shlex.quote(arg) for arg in args)
        shell_command = self._build_shell_command(command)

        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(coreg_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        combined_output = f"{result.stdout}\n{result.stderr}"
        if result.returncode != 0 or self._has_error_output(combined_output):
            return (
                "影像配准失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            "影像配准命令执行完成。\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )
####################影像裁剪############################
    def run_slc_copy_crop_all(
            self,
            list_file: str,
            coreg_dir: str,
            crop_dir: str,
            master_date: str,
            swath: str,
            polarization: str,
            data_format: str = "-",
            scale_factor: str = "-",
            crop_roff: str = "0",
            crop_nr: str = "1000",
            crop_loff: str = "0",
            crop_nl: str = "1000",
            timeout: int = 3600,
    ) -> str:
        list_path = Path(list_file).expanduser()
        coreg_path = Path(coreg_dir).expanduser()
        crop_path = Path(crop_dir).expanduser()

        print(">>> RUN SLC_copy CROP ALL", flush=True)
        print(f">>> list_file={list_path}", flush=True)
        print(f">>> coreg_dir={coreg_path}", flush=True)
        print(f">>> crop_dir={crop_path}", flush=True)
        print(f">>> master_date={master_date}", flush=True)
        print(f">>> swath={swath}", flush=True)
        print(f">>> polarization={polarization}", flush=True)

        if not list_path.exists():
            return f"裁剪失败：list_file 不存在：{list_path}"

        if not coreg_path.exists():
            return f"裁剪失败：coreg_dir 不存在：{coreg_path}"

        crop_path.mkdir(parents=True, exist_ok=True)

        dates = [
            line.strip()
            for line in list_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        if not dates:
            return f"裁剪失败：list_file 为空：{list_path}"

        try:
            range_offset = int(str(crop_roff).strip())
            range_count = int(str(crop_nr).strip())
            azimuth_offset = int(str(crop_loff).strip())
            azimuth_count = int(str(crop_nl).strip())
        except (TypeError, ValueError):
            return "裁剪失败：crop_roff、crop_nr、crop_loff、crop_nl 必须是整数。"

        if range_offset < 0 or azimuth_offset < 0 or range_count <= 0 or azimuth_count <= 0:
            return "裁剪失败：裁剪起始位置不能为负数，裁剪长度必须大于 0。"

        swath_text = str(swath).upper()
        pol_text = str(polarization).lower()

        logs = []

        for date in dates:
            date = str(date).strip()
            date_dir = coreg_path / date
            out_dir = crop_path / date

            if date == str(master_date):
                input_rslc = date_dir / f"{date}.rslc"
                input_par = date_dir / f"{date}.rslc.par"
            else:
                input_rslc = date_dir / f"{date}.{swath_text}_{pol_text}.rslc"
                input_par = date_dir / f"{date}.{swath_text}_{pol_text}.rslc.par"

            output_rslc = out_dir / f"{date}.rslc"
            output_par = out_dir / f"{date}.rslc.par"

            print(f">>> crop date={date}", flush=True)
            print(f">>> input_rslc={input_rslc}", flush=True)
            print(f">>> input_par={input_par}", flush=True)
            print(f">>> output_rslc={output_rslc}", flush=True)
            print(f">>> output_par={output_par}", flush=True)

            if not input_rslc.exists():
                logs.append(f"失败：输入 rslc 不存在：{input_rslc}")
                continue

            if not input_par.exists():
                logs.append(f"失败：输入 rslc.par 不存在：{input_par}")
                continue

            width_text = self._read_par_value(str(input_par), "range_samples")
            line_text = self._read_par_value(str(input_par), "azimuth_lines")
            try:
                source_width = int(width_text or "")
                source_lines = int(line_text or "")
            except ValueError:
                logs.append(
                    f"失败：无法从参数文件读取影像尺寸：{input_par}\n"
                    f"range_samples={width_text!r}, azimuth_lines={line_text!r}"
                )
                continue

            if range_offset + range_count > source_width or azimuth_offset + azimuth_count > source_lines:
                logs.append(
                    f"失败：{date} 的裁剪范围超出实际 RSLC 尺寸。\n"
                    f"输入尺寸：range_samples={source_width}, azimuth_lines={source_lines}\n"
                    f"请求范围：range={range_offset}:{range_offset + range_count}, "
                    f"azimuth={azimuth_offset}:{azimuth_offset + azimuth_count}"
                )
                continue

            if out_dir.exists() and any(out_dir.iterdir()):
                logs.append(
                    f"失败：裁剪输出目录已存在且非空，未覆盖旧结果：{out_dir}\n"
                    "请确认目录内容后手动移走它，或使用新的 crop_dir。"
                )
                continue

            out_dir.mkdir(parents=True, exist_ok=True)

            command = (
                f"SLC_copy "
                f"{shlex.quote(str(input_rslc))} "
                f"{shlex.quote(str(input_par))} "
                f"{shlex.quote(str(output_rslc))} "
                f"{shlex.quote(str(output_par))} "
                f"{shlex.quote(str(data_format))} "
                f"{shlex.quote(str(scale_factor))} "
                f"{shlex.quote(str(crop_roff))} "
                f"{shlex.quote(str(crop_nr))} "
                f"{shlex.quote(str(crop_loff))} "
                f"{shlex.quote(str(crop_nl))}"
            )

            shell_command = self._build_shell_command(command)

            print(f">>> command={command}", flush=True)

            result = subprocess.run(
                ["bash", "-lc", shell_command],
                cwd=str(out_dir),
                text=True,
                capture_output=True,
                timeout=timeout,
            )

            combined_output = f"{result.stdout}\n{result.stderr}"
            if result.returncode != 0 or self._has_error_output(combined_output):
                logs.append(
                    f"失败：{date}\n"
                    f"returncode={result.returncode}\n"
                    f"stdout:\n{result.stdout[-2000:]}\n"
                    f"stderr:\n{result.stderr[-2000:]}"
                )
            else:
                logs.append(
                    f"成功：{date}\n"
                    f"输出：{output_rslc}\n"
                    f"stdout:\n{result.stdout[-1000:]}\n"
                    f"stderr:\n{result.stderr[-1000:]}"
                )

        failed = [line for line in logs if line.startswith("失败")]
        if failed:
            return "## 裁剪完成，但存在失败项\n\n" + "\n\n".join(logs)

        return "## 裁剪全部完成\n\n" + "\n\n".join(logs)
##################生成rslc_tab文件#######################
    def write_rslc_tab_from_list(
            self,
            list_file: str,
            rslc_dir: str,
            rslc_tab: str,
            rslc_template: str = "$1/$1.rslc",
            rslc_par_template: str = "$1/$1.rslc.par",
    ) -> str:
        list_path = Path(list_file).expanduser()
        rslc_path = Path(rslc_dir).expanduser()
        rslc_tab_path = Path(rslc_tab).expanduser()

        print(">>> WRITE RSLC_tab from list", flush=True)
        print(f">>> list_file={list_path}", flush=True)
        print(f">>> rslc_dir={rslc_path}", flush=True)
        print(f">>> rslc_tab={rslc_tab_path}", flush=True)
        print(f">>> rslc_template={rslc_template}", flush=True)
        print(f">>> rslc_par_template={rslc_par_template}", flush=True)

        if not list_path.is_file():
            return f"list 文件不存在：{list_path}"

        if not rslc_path.exists():
            return f"RSLC 目录不存在：{rslc_path}"

        items = [
            line.strip()
            for line in list_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        lines = []
        missing_files = []

        for item in items:
            rslc_rel = rslc_template.replace("$1", item)
            rslc_par_rel = rslc_par_template.replace("$1", item)

            rslc_file = rslc_path / rslc_rel
            rslc_par_file = rslc_path / rslc_par_rel

            if not rslc_file.is_file():
                missing_files.append(str(rslc_file))

            if not rslc_par_file.is_file():
                missing_files.append(str(rslc_par_file))

            lines.append(f"{rslc_file}  {rslc_par_file}")

        if missing_files:
            return (
                    "生成 RSLC_tab 失败：以下文件不存在：\n"
                    + "\n".join(missing_files)
            )

        rslc_tab_path.parent.mkdir(parents=True, exist_ok=True)
        rslc_tab_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return (
                f"RSLC_tab 已生成：{rslc_tab_path}\n"
                + "\n".join(lines)
        )
#############生成itab文件####################
    def run_base_calc_itab(
            self,
            rslc_tab: str,
            master_rslc_par: str,
            bperp_file: str,
            itab_file: str,
            itab_type: str = "1",
            plot_flag: str = "1",
            bperp_min: str = "-",
            bperp_max: str = "200",
            delta_t_min: str = "-",
            delta_t_max: str = "37",
            delta_n_max: str = "2",
            timeout: int = 3600,
    ) -> str:
        rslc_tab_path = Path(rslc_tab).expanduser()
        master_rslc_par_path = Path(master_rslc_par).expanduser()
        bperp_path = Path(bperp_file).expanduser()
        itab_path = Path(itab_file).expanduser()

        print(">>> RUN base_calc", flush=True)
        print(f">>> rslc_tab={rslc_tab_path}", flush=True)
        print(f">>> master_rslc_par={master_rslc_par_path}", flush=True)
        print(f">>> bperp_file={bperp_path}", flush=True)
        print(f">>> itab_file={itab_path}", flush=True)
        print(f">>> itab_type={itab_type}", flush=True)
        print(f">>> plot_flag={plot_flag}", flush=True)
        print(f">>> bperp_min={bperp_min}", flush=True)
        print(f">>> bperp_max={bperp_max}", flush=True)
        print(f">>> delta_t_min={delta_t_min}", flush=True)
        print(f">>> delta_t_max={delta_t_max}", flush=True)
        print(f">>> delta_n_max={delta_n_max}", flush=True)

        if not rslc_tab_path.is_file():
            return f"RSLC_tab 文件不存在：{rslc_tab_path}"

        if not master_rslc_par_path.is_file():
            return f"主影像 RSLC 参数文件不存在：{master_rslc_par_path}"

        bperp_path.parent.mkdir(parents=True, exist_ok=True)
        itab_path.parent.mkdir(parents=True, exist_ok=True)

        args = [
            "base_calc",
            str(rslc_tab_path),
            str(master_rslc_par_path),
            str(bperp_path),
            str(itab_path),
            str(itab_type),
            str(plot_flag),
            str(bperp_min),
            str(bperp_max),
            str(delta_t_min),
            str(delta_t_max),
            str(delta_n_max),
        ]

        command = " ".join(shlex.quote(arg) for arg in args)
        shell_command = self._build_shell_command(command)

        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(itab_path.parent),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "生成 itab 失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            "生成 itab 命令执行完成。\n"
            f"bperp_file：{bperp_path}\n"
            f"itab_file：{itab_path}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )
################生成RMLI文件###################
    def run_mk_mli_all(
            self,
            rslc_tab: str,
            rmli_dir: str,
            rlks: str = "5",
            azlks: str = "1",
            timeout: int = 3600,
    ) -> str:
        rslc_tab_path = Path(rslc_tab).expanduser()
        rmli_path = Path(rmli_dir).expanduser()

        print(">>> RUN mk_mli_all", flush=True)
        print(f">>> rslc_tab={rslc_tab_path}", flush=True)
        print(f">>> rmli_dir={rmli_path}", flush=True)
        print(f">>> rlks={rlks}", flush=True)
        print(f">>> azlks={azlks}", flush=True)

        if not rslc_tab_path.is_file():
            return f"RSLC_tab 文件不存在：{rslc_tab_path}"

        rmli_path.mkdir(parents=True, exist_ok=True)

        args = [
            "mk_mli_all",
            str(rslc_tab_path),
            str(rmli_path),
            str(rlks),
            str(azlks),
        ]

        command = " ".join(shlex.quote(arg) for arg in args)
        shell_command = self._build_shell_command(command)

        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(rmli_path.parent),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "生成 RMLI 强度文件失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            "生成 RMLI 强度文件命令执行完成。\n"
            f"RMLI_dir：{rmli_path}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )
############常规差分干涉图###############
    def run_mk_diff_2d_initial(
            self,
            rslc_tab: str,
            itab_file: str,
            sar_dem: str,
            master_rmli: str,
            rmli_dir: str,
            diff_dir: str,
            rlks: str = "5",
            azlks: str = "1",
            diff_param_1: str = "3",
            s_value: str = "2",
            e_value: str = "0.1",
            timeout: int = 3600,
    ) -> str:
        return self.run_mk_diff_2d_command(
            args=[
                "mk_diff_2d",
                rslc_tab,
                itab_file,
                "0",
                sar_dem,
                "-",
                master_rmli,
                rmli_dir,
                diff_dir,
                rlks,
                azlks,
                diff_param_1,
                "-s",
                s_value,
                "-e",
                e_value,
            ],
            diff_dir=diff_dir,
            timeout=timeout,
            title="生成初始差分干涉图",
        )
    ##############使用傅里叶变化方法进行基线精化#################
    def run_mk_diff_2d_fourier_refine(
            self,
            rslc_tab: str,
            itab_file: str,
            sar_dem: str,
            master_rmli: str,
            rmli_dir: str,
            diff_dir: str,
            rlks: str = "5",
            azlks: str = "1",
            diff_param_1: str = "3",
            s_value: str = "2",
            e_value: str = "0.1",
            timeout: int = 3600,
    ) -> str:
        return self.run_mk_diff_2d_command(
            args=[
                "mk_diff_2d",
                rslc_tab,
                itab_file,
                "0",
                sar_dem,
                "-",
                master_rmli,
                rmli_dir,
                diff_dir,
                rlks,
                azlks,
                diff_param_1,
                "-i",
                "1",
                "-s",
                s_value,
                "-e",
                e_value,
            ],
            diff_dir=diff_dir,
            timeout=timeout,
            title="生成差分干涉图：傅里叶基线精化",
        )
    #############使用解缠相位最小二乘方法进行基线精化#######
    def run_mk_diff_2d_unw_refine(
            self,
            rslc_tab: str,
            itab_file: str,
            sar_dem: str,
            master_rmli: str,
            rmli_dir: str,
            diff_dir: str,
            diff2_dir: str,
            pbase_file: str,
            rlks: str = "5",
            azlks: str = "1",
            diff_param_1: str = "3",
            s_value: str = "2",
            e_value: str = "0.1",
            adf_alpha: str = "0.35",
            adf_window: str = "32",
            unw_alpha: str = "0.35",
            timeout: int = 3600,
    ) -> str:
        logs: list[str] = []
        diff_path = Path(diff_dir).expanduser()
        diff2_path = Path(diff2_dir).expanduser()
        diff2_path.mkdir(parents=True, exist_ok=True)
    ############通用命令##################
    def run_simple_command(
            self,
            args: list[str],
            cwd: str,
            title: str,
            timeout: int = 3600,
    ) -> str:
        cwd_path = Path(cwd).expanduser()
        cwd_path.mkdir(parents=True, exist_ok=True)

        command = " ".join(shlex.quote(str(arg)) for arg in args)
        shell_command = self._build_shell_command(command)

        print(f">>> RUN {title}", flush=True)
        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(cwd_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                f"{title}失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            f"{title}完成。\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )

    def run_mk_diff_2d_command(
            self,
            args: list[str],
            diff_dir: str,
            title: str,
            timeout: int = 3600,
    ) -> str:
        return self.run_simple_command(
            args=args,
            cwd=diff_dir,
            title=title,
            timeout=timeout,
        )
    ###################同质点选取######################
    def _read_par_value(self, par_file: str, key: str) -> str | None:
        path = Path(par_file).expanduser()

        if not path.exists():
            return None

        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                parts = line.strip().split()
                if not parts:
                    continue
                if parts[0].rstrip(":") == key.rstrip(":"):
                    if len(parts) >= 2:
                        return parts[1]

        return None

    def run_select_shp_matlab(
            self,
            rmli_dir: str,
            rmli_par: str,
            shp_output_dir: str,
            matlab_work_dir: str,
            matlab_func_dir: str,
            cal_win_range: str = "15",
            cal_win_azimuth: str = "15",
            alpha: str = "0.05",
            shp_method: str = "HTCI",
            matlab_command: str = "matlab",
            timeout: int = 7200,
    ) -> str:
        rmli_dir_path = Path(rmli_dir).expanduser()
        rmli_par_path = Path(rmli_par).expanduser()
        shp_output_path = Path(shp_output_dir).expanduser()
        matlab_work_path = Path(matlab_work_dir).expanduser()
        matlab_func_path = Path(matlab_func_dir).expanduser()

        if shp_method not in SHP_VARIABLE_BY_METHOD:
            return (
                f"未知SHP方法：{shp_method}\n"
                f"可选方法：{', '.join(SHP_VARIABLE_BY_METHOD.keys())}"
            )

        shp_variable = SHP_VARIABLE_BY_METHOD[shp_method]

        if not rmli_dir_path.exists():
            return f"RMLI目录不存在：{rmli_dir_path}"

        if not rmli_par_path.is_file():
            return f"RMLI参数文件不存在：{rmli_par_path}"

        if not matlab_func_path.exists():
            return f"MATLAB函数目录不存在：{matlab_func_path}"

        nlines = self._read_par_value(str(rmli_par_path), "azimuth_lines")
        if not nlines:
            return f"无法从参数文件读取 azimuth_lines：{rmli_par_path}"

        shp_output_path.mkdir(parents=True, exist_ok=True)
        matlab_work_path.mkdir(parents=True, exist_ok=True)

        output_mat = shp_output_path / f"{shp_variable}.mat"
        output_tif = shp_output_path / f"{shp_variable}_count.tif"
        script_path = matlab_work_path / "run_select_shp.m"

        matlab_code = f"""
    clear;
    clc;

    addpath('{matlab_func_path.as_posix()}');

    curpath = '{rmli_dir_path.as_posix()}';
    nlines = {nlines};

    rmlistack = ImgRead(curpath, 'rmli', nlines, 'float32');

    CalWin = [{cal_win_range} {cal_win_azimuth}];
    Alpha = {alpha};

    {shp_variable} = AllTest_SelPoint(rmlistack.datastack, CalWin, Alpha, '{shp_method}');

    save('{output_mat.as_posix()}', '{shp_variable}');

    try
        shp_count = sum({shp_variable}, 3);
        figure('visible', 'off');
        imagesc(shp_count);
        colorbar;
        title('{shp_variable} count');
        saveas(gcf, '{output_tif.as_posix()}');
    catch ME
        disp('SHP count figure skipped.');
        disp(ME.message);
    end

    disp('SHP selection finished.');
    disp('{output_mat.as_posix()}');
    """

        script_path.write_text(matlab_code, encoding="utf-8")

        command = f"{shlex.quote(matlab_command)} -batch {shlex.quote(script_path.stem)}"
        shell_command = self._build_shell_command(command)

        print(">>> RUN MATLAB SHP SELECT", flush=True)
        print(f">>> shp_method={shp_method}", flush=True)
        print(f">>> shp_variable={shp_variable}", flush=True)
        print(f">>> matlab_script={script_path}", flush=True)
        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(matlab_work_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "SHP选点失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        if not output_mat.exists():
            return (
                "SHP选点命令执行结束，但未找到输出文件。\n"
                f"期望输出：{output_mat}\n"
                f"stdout:\n{result.stdout[-2000:]}\n"
                f"stderr:\n{result.stderr[-2000:]}"
            )

        return (
            "SHP选点完成。\n"
            f"SHP变量：{shp_variable}\n"
            f"输出文件：{output_mat}\n"
            f"数量图：{output_tif}\n"
            f"MATLAB脚本：{script_path}"
        )
    ##############相位优化################
    ########读取 DIFF -> MATLAB EVD/EMI 相位优化 -> Goodness_fit 出图 -> 生成优化后的差分图##############
    def _read_par_value(self, par_file: str, key: str) -> str | None:
        path = Path(par_file).expanduser()

        if not path.is_file():
            return None

        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                parts = line.strip().split()
                if not parts:
                    continue

                current_key = parts[0].rstrip(":")
                target_key = key.rstrip(":")

                if current_key == target_key and len(parts) >= 2:
                    return parts[1]

        return None

    def _read_diff_stack_shape(self, diff_dir: str) -> tuple[str, str, list[Path]] | str:
        diff_path = Path(diff_dir).expanduser()

        if not diff_path.exists():
            return f"DIFF目录不存在：{diff_path}"

        off_files = sorted(diff_path.glob("*.off"))

        if not off_files:
            return f"DIFF目录下没有找到 *.off 文件：{diff_path}"

        shapes: list[tuple[Path, str, str]] = []

        for off_file in off_files:
            width = self._read_par_value(str(off_file), "interferogram_width")
            lines = self._read_par_value(str(off_file), "interferogram_azimuth_lines")

            if not width or not lines:
                return (
                    f"无法从 {off_file} 读取 interferogram_width "
                    "或 interferogram_azimuth_lines"
                )

            shapes.append((off_file, width, lines))

        unique_shapes = {(width, lines) for _, width, lines in shapes}

        if len(unique_shapes) != 1:
            report = "\n".join(
                f"{off_file}: width={width}, lines={lines}"
                for off_file, width, lines in shapes
            )
            return (
                "DIFF目录中的 .off 文件尺寸不一致，不能自动确定统一尺寸。\n"
                f"{report}"
            )

        _, width, lines = shapes[0]
        return width, lines, off_files

    def run_phase_optimization_workflow(
            self,
            diff_dir: str,
            phase_opt_output_dir: str,
            matlab_work_dir: str,
            matlab_func_dir: str,
            phase_opt_method: str,
            fit_threshold: str,
            shp_output_dir: str,
            shp_method: str,
            ref_id: str = "1",
            block_size: str = "1",
            matlab_command: str = "matlab",
            output_name: str = "phase_opt",
            timeout: int = 7200,
    ) -> str:
        diff_path = Path(diff_dir).expanduser()
        output_path = Path(phase_opt_output_dir).expanduser()
        work_path = Path(matlab_work_dir).expanduser()
        func_path = Path(matlab_func_dir).expanduser()
        shp_output_path = Path(shp_output_dir).expanduser()

        if not diff_path.exists():
            return f"DIFF目录不存在：{diff_path}"

        if not func_path.exists():
            return f"MATLAB函数目录不存在：{func_path}"

        if not shp_output_path.exists():
            return f"SHP输出目录不存在：{shp_output_path}"

        if shp_method not in SHP_VARIABLE_BY_METHOD:
            return (
                f"未知SHP方法：{shp_method}\n"
                f"可选方法：{', '.join(SHP_VARIABLE_BY_METHOD.keys())}"
            )

        shp_variable = SHP_VARIABLE_BY_METHOD[shp_method]
        shp_mat_path = shp_output_path / f"{shp_variable}.mat"

        if not shp_mat_path.is_file():
            return (
                "SHP结果文件不存在，请先执行2.5同质像元选取。\n"
                f"期望文件：{shp_mat_path}"
            )

        shape_result = self._read_diff_stack_shape(str(diff_path))

        if isinstance(shape_result, str):
            return shape_result

        nwidths, nlines, off_files = shape_result

        output_path.mkdir(parents=True, exist_ok=True)
        work_path.mkdir(parents=True, exist_ok=True)

        method_map = {
            "evd_ps_single": (
                f"Opt = EVD_PSDeDiff_Single(diffstack, {shp_variable}, "
                f"{ref_id}, {fit_threshold});"
            ),
            "emi_ps_single": (
                f"Opt = EMI_PSDeDiff_Single(diffstack, {shp_variable}, "
                f"{ref_id}, {fit_threshold});"
            ),
            "evd_sbas_single": (
                f"Opt = EVD_SBASDeDiff_Single(diffstack, {shp_variable}, "
                f"{fit_threshold});"
            ),
            "emi_sbas_single": (
                f"Opt = EMI_SBASDeDiff_Single(diffstack, {shp_variable}, "
                f"{fit_threshold});"
            ),
            "evd_ps_block": (
                f"Opt = EVD_PSDeDiff_Block(diffstack, {shp_variable}, "
                f"{ref_id}, {fit_threshold}, {block_size});"
            ),
            "emi_ps_block": (
                f"Opt = EMI_PSDeDiff_Block(diffstack, {shp_variable}, "
                f"{ref_id}, {fit_threshold}, {block_size});"
            ),
            "evd_sbas_block": (
                f"Opt = EVD_SBASDeDiff_Block(diffstack, {shp_variable}, "
                f"{fit_threshold}, {block_size});"
            ),
            "emi_sbas_block": (
                f"Opt = EMI_SBASDeDiff_Block(diffstack, {shp_variable}, "
                f"{fit_threshold}, {block_size});"
            ),
        }

        if phase_opt_method not in method_map:
            return (
                f"未知相位优化方法：{phase_opt_method}\n"
                f"可选方法：{', '.join(method_map.keys())}"
            )

        output_mat = output_path / f"{output_name}.mat"
        goodness_png = output_path / f"{output_name}_goodness.png"
        script_path = work_path / "run_phase_optimization.m"

        matlab_code = f"""
    clear;
    clc;

    addpath(genpath('{func_path.as_posix()}'));

    curpath = '{diff_path.as_posix()}';
    diff_lines = {nlines};
    nlines = {nlines};
    nwidths = {nwidths};

    if exist('fit.mat', 'file')
        delete('fit.mat');
    end

    diffstack = ImgRead(curpath, 'diff', diff_lines, 'cpxfloat32');

    load('{shp_mat_path.as_posix()}');

    if ~exist('{shp_variable}', 'var')
        error('SHP variable not found: {shp_variable}');
    end

    {method_map[phase_opt_method]}

    save('{output_mat.as_posix()}', 'Opt');

    if exist('fit.mat', 'file')
        load('fit.mat');

        if exist('goodness_fit', 'var')
            save('{output_mat.as_posix()}', 'Opt', 'goodness_fit');

            Goodness_fit = reshape(goodness_fit, nlines, nwidths);
            figure('visible', 'off');
            imagesc(Goodness_fit);
            colorbar;
            title('Goodness fit');
            saveas(gcf, '{goodness_png.as_posix()}');

            disp('Goodness_fit saved.');
            disp('{goodness_png.as_posix()}');
        else
            disp('fit.mat exists but goodness_fit variable not found.');
        end
    else
        disp('fit.mat generated by phase optimization function not found.');
    end

    for vv = 1:size(Opt.cpx, 1)
        absdata = abs(reshape(Opt.cpx(vv,:), nlines, nwidths));
        phadata = angle(reshape(Opt.cpx(vv,:), nlines, nwidths));

        pair_mat = fullfile('{output_path.as_posix()}', sprintf('opt_pair_%d.mat', vv));
        phase_png = fullfile('{output_path.as_posix()}', sprintf('opt_phase_%d.png', vv));
        abs_png = fullfile('{output_path.as_posix()}', sprintf('opt_abs_%d.png', vv));

        save(pair_mat, 'absdata', 'phadata');

        figure('visible', 'off');
        imagesc(phadata);
        colorbar;
        title(sprintf('Optimized phase %d', vv));
        saveas(gcf, phase_png);

        figure('visible', 'off');
        imagesc(absdata);
        colorbar;
        title(sprintf('Optimized amplitude %d', vv));
        saveas(gcf, abs_png);

        disp('Optimized phase image saved.');
        disp(phase_png);
        disp('Optimized amplitude image saved.');
        disp(abs_png);
    end

    disp('Phase optimization finished.');
    disp('{output_mat.as_posix()}');
    """

        script_path.write_text(matlab_code, encoding="utf-8")

        matlab_cmd = f"{shlex.quote(matlab_command)} -batch {shlex.quote(script_path.stem)}"
        shell_command = self._build_shell_command(matlab_cmd)

        print(">>> RUN PHASE OPTIMIZATION WORKFLOW", flush=True)
        print(f">>> diff_dir={diff_path}", flush=True)
        print(f">>> off_file_count={len(off_files)}", flush=True)
        print(f">>> nlines={nlines}", flush=True)
        print(f">>> nwidths={nwidths}", flush=True)
        print(f">>> shp_method={shp_method}", flush=True)
        print(f">>> shp_variable={shp_variable}", flush=True)
        print(f">>> shp_mat={shp_mat_path}", flush=True)
        print(f">>> phase_opt_method={phase_opt_method}", flush=True)
        print(f">>> fit_threshold={fit_threshold}", flush=True)
        print(f">>> output_mat={output_mat}", flush=True)
        print(f">>> matlab_script={script_path}", flush=True)
        print(f">>> command={matlab_cmd}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(work_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "相位优化失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        if not output_mat.exists():
            return f"相位优化执行结束，但未找到输出文件：{output_mat}"

        outputs = sorted(output_path.glob("opt_*.png"))

        report = [
            "相位优化完成。",
            f"输出文件：{output_mat}",
            f"Goodness图：{goodness_png if goodness_png.exists() else '未生成'}",
        ]

        if outputs:
            report.append("优化后图像：")
            report.extend(str(path) for path in outputs)

        return "\n".join(report)
    ################数据整理#######################
    def _link_file(self, source: Path, target: Path) -> str | None:
        if not source.is_file():
            return f"源文件不存在：{source}"

        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() or target.is_symlink():
            if target.is_symlink():
                target.unlink()
            else:
                return f"目标文件已存在且不是软链接，为避免覆盖已停止：{target}"

        target.symlink_to(source)
        return None

    def _read_nonempty_lines(self, path: Path) -> list[str]:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return [
                line.strip()
                for line in handle
                if line.strip() and not line.strip().startswith("#")
            ]

    def _read_bperp_pairs(self, bperp_file: Path) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []

        with bperp_file.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                text = line.strip()
                if not text or text.startswith("#"):
                    continue

                parts = text.split()
                if len(parts) < 3:
                    continue

                pairs.append((parts[1], parts[2]))

        return pairs

    def run_file_construct(
            self,
            geo_dir: str,
            ts_flag: str,
            rslc_dir: str,
            diff_dir: str,
            phase_opt_output_dir: str,
            list_file: str,
            bperp_file: str,
            rmli_dir: str,
            master_date: str,
            timeout: int = 3600,
    ) -> str:
        geo_path = Path(geo_dir).expanduser()
        rslc_path = Path(rslc_dir).expanduser()
        original_diff_path = Path(diff_dir).expanduser()
        phase_opt_path = Path(phase_opt_output_dir).expanduser()
        list_path = Path(list_file).expanduser()
        bperp_path = Path(bperp_file).expanduser()
        rmli_path = Path(rmli_dir).expanduser()

        if str(ts_flag) not in {"0", "1"}:
            return f"ts_flag 只能是 0 或 1，当前为：{ts_flag}"

        required_dirs = {
            "GEO_DIR(diff_geo_dir)": geo_path,
            "rslc_dir": rslc_path,
            "diff_dir": original_diff_path,
            "phase_opt_output_dir": phase_opt_path,
            "RMLI_DIR(rmli_dir)": rmli_path,
        }

        for name, path in required_dirs.items():
            if not path.exists():
                return f"{name} 不存在：{path}"

        required_files = {
            "list_file": list_path,
            "bperp_file": bperp_path,
        }

        for name, path in required_files.items():
            if not path.is_file():
                return f"{name} 不存在：{path}"

        dates = self._read_nonempty_lines(list_path)

        if master_date and master_date not in dates:
            dates.append(str(master_date))

        pairs = self._read_bperp_pairs(bperp_path)

        if not pairs:
            return f"无法从 bperp_file 读取干涉对信息：{bperp_path}"

        staging_root = phase_opt_path / "_file_construct_inputs"
        flat_slc_dir = staging_root / "SLC_flat"
        construct_diff_dir = phase_opt_path

        errors: list[str] = []
        warnings: list[str] = []

        for date in dates:
            src_rslc = rslc_path / date / f"{date}.rslc"
            src_par = rslc_path / date / f"{date}.rslc.par"

            dst_rslc = flat_slc_dir / f"{date}.rslc"
            dst_par = flat_slc_dir / f"{date}.rslc.par"

            error = self._link_file(src_rslc, dst_rslc)
            if error:
                errors.append(error)

            error = self._link_file(src_par, dst_par)
            if error:
                errors.append(error)

        for master, slave in pairs:
            pair_name = f"{master}_{slave}"

            src_base = original_diff_path / f"{pair_name}.base"
            dst_base = construct_diff_dir / f"{pair_name}.base"

            error = self._link_file(src_base, dst_base)
            if error:
                errors.append(error)

            optimized_diff = phase_opt_path / f"{pair_name}.diff"
            original_diff = original_diff_path / f"{pair_name}.diff"
            dst_diff = construct_diff_dir / f"{pair_name}.diff"

            if optimized_diff.is_file():
                source_diff = optimized_diff
            elif original_diff.is_file():
                source_diff = original_diff
                warnings.append(
                    f"未找到相位优化后的 {optimized_diff.name}，暂时使用原始差分干涉图：{original_diff}"
                )
            else:
                errors.append(
                    f"缺少差分干涉图：既不存在 {optimized_diff}，也不存在 {original_diff}"
                )
                continue

            if source_diff.resolve() != dst_diff.resolve():
                error = self._link_file(source_diff, dst_diff)
                if error:
                    errors.append(error)

        if errors:
            return (
                    "file_construct 前置文件准备失败。\n\n"
                    "缺失或冲突文件：\n"
                    + "\n".join(f"- {item}" for item in errors)
            )

        command = (
            f"file_construct "
            f"{shlex.quote(str(geo_path))} "
            f"{shlex.quote(str(ts_flag))} "
            f"{shlex.quote(str(flat_slc_dir))} "
            f"{shlex.quote(str(construct_diff_dir))} "
            f"{shlex.quote(str(construct_diff_dir))} "
            f"{shlex.quote(str(list_path))} "
            f"{shlex.quote(str(bperp_path))} "
            f"{shlex.quote(str(rmli_path))}"
        )

        shell_command = self._build_shell_command(command)

        print(">>> RUN file_construct", flush=True)
        print(f">>> GEO_DIR={geo_path}", flush=True)
        print(f">>> ts_flag={ts_flag}", flush=True)
        print(f">>> SLC_DIR(flat)={flat_slc_dir}", flush=True)
        print(f">>> DIFF_DIR={construct_diff_dir}", flush=True)
        print(f">>> base_dir={construct_diff_dir}", flush=True)
        print(f">>> list_file={list_path}", flush=True)
        print(f">>> bperp_file={bperp_path}", flush=True)
        print(f">>> RMLI_DIR={rmli_path}", flush=True)
        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(construct_diff_dir),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "file_construct 执行失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        ts_dir = construct_diff_dir / "TS"

        report = [
            "file_construct 执行完成。",
            f"TS目录：{ts_dir if ts_dir.exists() else '未检测到，需查看脚本输出'}",
            f"平铺SLC临时目录：{flat_slc_dir}",
        ]

        if warnings:
            report.append("警告：")
            report.extend(f"- {item}" for item in warnings)

        report.append(f"stdout:\n{result.stdout[-2000:]}")
        report.append(f"stderr:\n{result.stderr[-2000:]}")

        return "\n\n".join(report)
    ###############psc选点####################
    def run_mt_prep_gamma(
            self,
            master_date: str,
            ts_dir: str,
            ts_flag: str,
            da_thresh: str,
            rg_patches: str = "1",
            az_patches: str = "1",
            rg_overlap: str = "50",
            az_overlap: str = "50",
            mask_file: str | None = None,
            timeout: int = 3600,
    ) -> str:
        ts_path = Path(ts_dir).expanduser()

        if not ts_path.exists():
            return f"TS目录不存在：{ts_path}"

        if str(ts_flag) == "0":
            work_dir = ts_path / "PDS-TS"
        elif str(ts_flag) == "1":
            work_dir = ts_path / "PS-TS"
        else:
            return f"ts_flag 只能是 0 或 1，当前为：{ts_flag}"

        work_dir.mkdir(parents=True, exist_ok=True)

        args = [
            "mt_prep_gamma",
            str(master_date),
            str(ts_path),
            str(da_thresh),
            str(rg_patches),
            str(az_patches),
            str(rg_overlap),
            str(az_overlap),
        ]

        if mask_file:
            mask_path = Path(mask_file).expanduser()
            if not mask_path.is_file():
                return f"mask_file 不存在：{mask_path}"
            args.append(str(mask_path))

        command = " ".join(shlex.quote(item) for item in args)
        shell_command = self._build_shell_command(command)

        print(">>> RUN mt_prep_gamma", flush=True)
        print(f">>> master_date={master_date}", flush=True)
        print(f">>> ts_flag={ts_flag}", flush=True)
        print(f">>> work_dir={work_dir}", flush=True)
        print(f">>> ts_dir={ts_path}", flush=True)
        print(f">>> da_thresh={da_thresh}", flush=True)
        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(work_dir),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        number_lines = []
        for line in (result.stdout + "\n" + result.stderr).splitlines():
            if "number" in line.lower():
                number_lines.append(line)

        if result.returncode != 0:
            return (
                    "mt_prep_gamma 执行失败。\n"
                    f"returncode={result.returncode}\n"
                    f"stdout:\n{result.stdout}\n"
                    f"stderr:\n{result.stderr}\n"
                    f"number相关输出:\n" + "\n".join(number_lines[-20:])
            )

        expected_files = [
            work_dir / "pscphase.in",
            work_dir / "pscdem.in",
            work_dir / "pscands.1.ij",
            work_dir / "pt2geo.in",
        ]

        existing = [path for path in expected_files if path.exists()]

        return (
                "mt_prep_gamma 执行完成。\n"
                f"工作目录：{work_dir}\n"
                f"TS数据目录：{ts_path}\n"
                f"number相关输出:\n" + "\n".join(number_lines[-20:]) + "\n"
                                                                       f"检测到输出文件：\n" + "\n".join(
            str(path) for path in existing) + "\n"
                                              f"stdout:\n{result.stdout[-2000:]}\n"
                                              f"stderr:\n{result.stderr[-2000:]}"
        )
    ############dsc以及psds融合###########
    def run_dsc_select_matlab(
            self,
            ts_dir: str,
            diff_shape_dir: str,
            phase_opt_mat: str,
            matlab_work_dir: str,
            matlab_func_dir: str,
            fit_threshold: str,
            rg_patches: str = "1",
            az_patches: str = "1",
            rg_overlap: str = "50",
            az_overlap: str = "50",
            matlab_command: str = "matlab",
            timeout: int = 7200,
    ) -> str:
        ts_path = Path(ts_dir).expanduser()
        diff_shape_path = Path(diff_shape_dir).expanduser()
        phase_opt_path = Path(phase_opt_mat).expanduser()
        work_path = Path(matlab_work_dir).expanduser()
        func_path = Path(matlab_func_dir).expanduser()

        if not ts_path.exists():
            return f"TS目录不存在：{ts_path}"
        if not diff_shape_path.exists():
            return f"差分干涉尺寸来源目录不存在：{diff_shape_path}"
        if not phase_opt_path.is_file():
            return f"相位优化结果文件不存在：{phase_opt_path}"
        if not func_path.exists():
            return f"MATLAB函数目录不存在：{func_path}"

        shape_result = self._read_diff_stack_shape(str(diff_shape_path))
        if isinstance(shape_result, str):
            return shape_result

        nwidths, nlines, _ = shape_result

        work_path.mkdir(parents=True, exist_ok=True)
        script_path = work_path / "run_dsc_select.m"

        matlab_code = f"""
    clear;
    clc;

    addpath(genpath('{func_path.as_posix()}'));
    cd('{ts_path.as_posix()}');

    load('{phase_opt_path.as_posix()}');

    if ~exist('goodness_fit', 'var')
        error('goodness_fit variable not found in phase optimization mat file.');
    end

    nlines = {nlines};
    nwidths = {nwidths};
    fit = {fit_threshold};
    rg_patches = {rg_patches};
    az_patches = {az_patches};
    rg_overlap = {rg_overlap};
    az_overlap = {az_overlap};

    DSC_Select(goodness_fit, nlines, nwidths, fit, rg_patches, az_patches, rg_overlap, az_overlap);

    disp('DSC_Select finished.');
    """

        script_path.write_text(matlab_code, encoding="utf-8")

        batch_expr = f"run('{script_path.as_posix()}')"
        command = f"{shlex.quote(matlab_command)} -batch {shlex.quote(batch_expr)}"
        shell_command = self._build_shell_command(command)

        print(">>> RUN DSC_Select", flush=True)
        print(f">>> ts_dir={ts_path}", flush=True)
        print(f">>> diff_shape_dir={diff_shape_path}", flush=True)
        print(f">>> phase_opt_mat={phase_opt_path}", flush=True)
        print(f">>> nlines={nlines}", flush=True)
        print(f">>> nwidths={nwidths}", flush=True)
        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(ts_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "DSC_Select 执行失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            "DSC_Select 执行完成。\n"
            f"TS目录：{ts_path}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )

    def run_pds_merge_matlab(
            self,
            ts_dir: str,
            matlab_work_dir: str,
            matlab_func_dir: str,
            fit_threshold: str,
            rg_patches: str = "1",
            az_patches: str = "1",
            ts_flag: str = "1",
            matlab_command: str = "matlab",
            timeout: int = 7200,
    ) -> str:
        ts_path = Path(ts_dir).expanduser()
        work_path = Path(matlab_work_dir).expanduser()
        func_path = Path(matlab_func_dir).expanduser()

        if not ts_path.exists():
            return f"TS目录不存在：{ts_path}"
        if not func_path.exists():
            return f"MATLAB函数目录不存在：{func_path}"

        patches_num = int(str(rg_patches)) * int(str(az_patches))
        is_sbas = "1" if str(ts_flag) == "1" else "0"

        work_path.mkdir(parents=True, exist_ok=True)
        script_path = work_path / "run_pds_merge.m"

        matlab_code = f"""
    clear;
    clc;

    addpath(genpath('{func_path.as_posix()}'));
    cd('{ts_path.as_posix()}');

    fit_threshold = {fit_threshold};
    patches_num = {patches_num};
    isSBAS = {is_sbas};

    PDS_Merge(fit_threshold, patches_num, isSBAS);

    disp('PDS_Merge finished.');
    """

        script_path.write_text(matlab_code, encoding="utf-8")

        batch_expr = f"run('{script_path.as_posix()}')"
        command = f"{shlex.quote(matlab_command)} -batch {shlex.quote(batch_expr)}"
        shell_command = self._build_shell_command(command)

        print(">>> RUN PDS_Merge", flush=True)
        print(f">>> ts_dir={ts_path}", flush=True)
        print(f">>> patches_num={patches_num}", flush=True)
        print(f">>> isSBAS={is_sbas}", flush=True)
        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(ts_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "PDS_Merge 执行失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            "PDS_Merge 执行完成。\n"
            f"TS目录：{ts_path}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )

    def run_mt_prep_gamma_addds(
            self,
            master_date: str,
            ts_dir: str,
            da_thresh: str,
            rg_patches: str = "1",
            az_patches: str = "1",
            rg_overlap: str = "50",
            az_overlap: str = "50",
            mt_prep_gamma_addds_command: str = "mt_prep_gamma_addDS",
            timeout: int = 3600,
    ) -> str:
        ts_path = Path(ts_dir).expanduser()

        if not ts_path.exists():
            return f"TS目录不存在：{ts_path}"

        if "/" in mt_prep_gamma_addds_command:
            command_path = Path(mt_prep_gamma_addds_command).expanduser()
            if not command_path.is_file():
                return f"mt_prep_gamma_addDS 命令不存在：{command_path}"
            command_name = str(command_path)
        else:
            command_name = mt_prep_gamma_addds_command

        args = [
            command_name,
            str(master_date),
            str(ts_path),
            str(da_thresh),
            str(rg_patches),
            str(az_patches),
            str(rg_overlap),
            str(az_overlap),
        ]

        command = " ".join(shlex.quote(item) for item in args)
        shell_command = self._build_shell_command(command)

        print(">>> RUN mt_prep_gamma_addDS", flush=True)
        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(ts_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "mt_prep_gamma_addDS 执行失败。\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        return (
            "mt_prep_gamma_addDS 执行完成。\n"
            f"TS目录：{ts_path}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )

    def run_dsc_pds_workflow(
            self,
            master_date: str,
            ts_dir: str,
            diff_shape_dir: str,
            phase_opt_mat: str,
            matlab_work_dir: str,
            matlab_func_dir: str,
            fit_threshold: str,
            rg_patches: str = "1",
            az_patches: str = "1",
            rg_overlap: str = "50",
            az_overlap: str = "50",
            ts_flag: str = "1",
            matlab_command: str = "matlab",
            mt_prep_gamma_addds_command: str = "mt_prep_gamma_addDS",
    ) -> str:
        logs = []

        logs.append(
            self.run_dsc_select_matlab(
                ts_dir=ts_dir,
                diff_shape_dir=diff_shape_dir,
                phase_opt_mat=phase_opt_mat,
                matlab_work_dir=matlab_work_dir,
                matlab_func_dir=matlab_func_dir,
                fit_threshold=fit_threshold,
                rg_patches=rg_patches,
                az_patches=az_patches,
                rg_overlap=rg_overlap,
                az_overlap=az_overlap,
                matlab_command=matlab_command,
            )
        )

        logs.append(
            self.run_pds_merge_matlab(
                ts_dir=ts_dir,
                matlab_work_dir=matlab_work_dir,
                matlab_func_dir=matlab_func_dir,
                fit_threshold=fit_threshold,
                rg_patches=rg_patches,
                az_patches=az_patches,
                ts_flag=ts_flag,
                matlab_command=matlab_command,
            )
        )

        logs.append(
            self.run_mt_prep_gamma_addds(
                master_date=master_date,
                ts_dir=ts_dir,
                da_thresh=fit_threshold,
                rg_patches=rg_patches,
                az_patches=az_patches,
                rg_overlap=rg_overlap,
                az_overlap=az_overlap,
                mt_prep_gamma_addds_command=mt_prep_gamma_addds_command,
            )
        )

        return "\n\n".join(logs)
    ###################stamps处理################
    def run_stamps_processing(
            self,
            stamps_work_dir: str,
            stamps_mode: str = "sbas",
            matlab_command: str = "matlab",
            timeout: int = 21600,
    ) -> str:
        work_path = Path(stamps_work_dir).expanduser()
        mode = str(stamps_mode).lower()

        print(">>> RUN STAMPS PROCESSING", flush=True)
        print(f">>> stamps_work_dir={work_path}", flush=True)
        print(f">>> stamps_mode={mode}", flush=True)
        print(f">>> matlab_command={matlab_command}", flush=True)

        if not work_path.exists():
            return f"StaMPS 工作目录不存在：{work_path}"

        if not work_path.is_dir():
            return f"StaMPS 工作路径不是目录：{work_path}"

        if mode == "ps":
            params = {
                "weed_neighbours": "n",
                "weed_standard_dev": 1.5,
                "weed_max_noise": 10,
                "merge_resample_size": 0,
                "unwrap_method": "3D_QUICK",
                "unwrap_grid_size": 40,
                "unwrap_gold_n_win": 96,
                "unwrap_gold_alpha": 0.9,
                "scla_deramp": "y",
                "plot_scatterer_size": 20,
                "density_rand": 20,
                "percent_rand": 20,
            }
        elif mode == "sbas":
            params = {
                "weed_neighbours": "n",
                "weed_standard_dev": 1.5,
                "weed_max_noise": 10,
                "merge_resample_size": 0,
                "unwrap_method": "3D_QUICK",
                "unwrap_grid_size": 40,
                "unwrap_gold_n_win": 96,
                "unwrap_gold_alpha": 0.9,
                "scla_deramp": "y",
                "plot_scatterer_size": 20,
                "density_rand": 20,
                "percent_rand": 20,
            }
        elif mode == "ds":
            params = {
                "weed_neighbours": "n",
                "weed_standard_dev": 0.5,
                "weed_max_noise": 1.2,
                "merge_resample_size": 0,
                "unwrap_method": "3D_QUICK",
                "unwrap_grid_size": 40,
                "unwrap_gold_n_win": 64,
                "unwrap_gold_alpha": 0.8,
                "scla_deramp": "y",
                "plot_scatterer_size": 20,
            }
        else:
            return "stamps_mode 参数错误：只能是 ps / sbas / ds"

        matlab_lines = [
            "try",
            f"cd('{str(work_path)}');",
            "disp(['StaMPS work dir: ', pwd]);",
        ]

        for key, value in params.items():
            if isinstance(value, str):
                matlab_lines.append(f"safe_setparm('{key}', '{value}');")
            else:
                matlab_lines.append(f"safe_setparm('{key}', {value});")

        matlab_lines.extend(
            [
                "getparm;",
                "stamps(1,7);",
                "catch ME",
                "disp(getReport(ME, 'extended'));",
                "exit(1);",
                "end",
                "exit(0);",
                "",
                "function safe_setparm(name, value)",
                "try",
                "setparm(name, value);",
                "catch ME",
                "disp(['setparm skipped: ', name, ' -> ', ME.message]);",
                "end",
                "end",
            ]
        )

        script_path = work_path / "run_stamps_processing.m"
        script_path.write_text("\n".join(matlab_lines), encoding="utf-8")

        command = f"{shlex.quote(matlab_command)} -batch run_stamps_processing"

        shell_command = self._build_shell_command(command)

        print(f">>> matlab_script={script_path}", flush=True)
        print(f">>> command={command}", flush=True)

        result = subprocess.run(
            ["bash", "-lc", shell_command],
            cwd=str(work_path),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return (
                "## StaMPS 处理执行失败\n\n"
                f"工作目录：{work_path}\n\n"
                "### stdout\n"
                f"```text\n{result.stdout[-4000:]}\n```\n\n"
                "### stderr\n"
                f"```text\n{result.stderr[-4000:]}\n```"
            )

        return (
            "## StaMPS 处理执行完成\n\n"
            f"工作目录：{work_path}\n\n"
            "### stdout\n"
            f"```text\n{result.stdout[-4000:]}\n```\n\n"
            "### stderr\n"
            f"```text\n{result.stderr[-2000:]}\n```"
        )
