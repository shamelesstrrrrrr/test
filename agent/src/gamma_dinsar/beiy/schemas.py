from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class DInSARTaskInput(BaseModel):
    task_id: str | None = Field(default=None, description="任务ID")
    master_slc: Path | None = Field(default=None, description="前时相Sentinel-1 IW SLC路径")
    slave_slc: Path | None = Field(default=None, description="后时相Sentinel-1 IW SLC路径")
    aoi: Path | None = Field(default=None, description="AOI文件路径")
    dem: Path | None = Field(default=None, description="DEM文件路径")
    polarization: Literal["VV", "VH", "HH", "HV"] = "VV"
    output_dir: Path | None = Field(default=None, description="输出目录")
    resume: bool = False

    def missing_fields(self) -> list[str]:
        missing = []
        for field_name in ["task_id", "master_slc", "slave_slc", "aoi", "dem", "output_dir"]:
            if getattr(self, field_name) is None:
                missing.append(field_name)
        return missing

    def is_complete(self) -> bool:
        return len(self.missing_fields()) == 0