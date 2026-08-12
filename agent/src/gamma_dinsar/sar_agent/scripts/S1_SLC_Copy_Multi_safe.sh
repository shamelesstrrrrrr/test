#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: S1_SLC_Copy_Multi_safe.sh <SLC_DIR> <BURST_DIR> <pol> <swath> <bn_start1> <bn_end1> [bn_start2 bn_end2] [bn_start3 bn_end3]

pol:
  0 or VV: vv
  1 or VH: vh

swath (the same codes used by S1_SLC_Normal and S1_SLC_COREG_Multi):
  1: IW1
  2: IW2
  3: IW3
  4: IW1+IW2
  5: IW1+IW3
  6: IW2+IW3
  7: IW1+IW2+IW3
EOF
}

if [[ $# -lt 6 || $# -gt 10 ]]; then
  usage >&2
  exit 1
fi

slc_dir=$1
burst_dir=$2
pol_mode=$3
swath_code=$4
shift 4

if (( $# % 2 != 0 )); then
  echo "ERROR: burst start/end parameters must be supplied in pairs" >&2
  exit 1
fi

case "${pol_mode^^}" in
  0|VV) pol="vv" ;;
  1|VH) pol="vh" ;;
  *)
    echo "ERROR: invalid polarization: ${pol_mode}" >&2
    exit 1
    ;;
esac

case "$swath_code" in
  1) selected_swaths=("IW1") ;;
  2) selected_swaths=("IW2") ;;
  3) selected_swaths=("IW3") ;;
  4) selected_swaths=("IW1" "IW2") ;;
  5) selected_swaths=("IW1" "IW3") ;;
  6) selected_swaths=("IW2" "IW3") ;;
  7) selected_swaths=("IW1" "IW2" "IW3") ;;
  *)
    echo "ERROR: invalid swath code: ${swath_code}" >&2
    exit 1
    ;;
esac

burst_pairs=("$@")
expected_pair_count=${#selected_swaths[@]}
actual_pair_count=$((${#burst_pairs[@]} / 2))

if [[ "$actual_pair_count" -ne "$expected_pair_count" ]]; then
  echo "ERROR: swath code ${swath_code} requires ${expected_pair_count} burst start/end pair(s), got ${actual_pair_count}" >&2
  exit 1
fi

if [[ ! -d "$slc_dir" ]]; then
  echo "ERROR: SLC directory does not exist: ${slc_dir}" >&2
  exit 1
fi

date_dirs=()
while IFS= read -r child; do
  date_name=$(basename "$child")
  if [[ "$date_name" =~ ^[0-9]{8}$ && -f "$child/SLC_tab" ]]; then
    date_dirs+=("$date_name")
  fi
done < <(find "$slc_dir" -mindepth 1 -maxdepth 1 -type d -print | sort)

if [[ "${#date_dirs[@]}" -eq 0 ]]; then
  echo "ERROR: no YYYYMMDD directories with SLC_tab found under ${slc_dir}" >&2
  exit 1
fi

mkdir -p "$burst_dir"
printf "%s\n" "${date_dirs[@]}" > "$burst_dir/list"

filter_tab_to_swaths() {
  local tab_file=$1
  shift
  local keep_swaths=("$@")
  local swath_name
  local keep

  for swath_name in IW1 IW2 IW3; do
    keep=false
    for candidate in "${keep_swaths[@]}"; do
      if [[ "$candidate" == "$swath_name" ]]; then
        keep=true
        break
      fi
    done
    if [[ "$keep" == false ]]; then
      sed -i "/${swath_name}/d" "$tab_file"
    fi
  done
}

slc_format_code() {
  local par_file=$1
  local format_text
  format_text=$(awk '/image_format:/ {print $2; exit}' "$par_file")
  if [[ "$format_text" == "FCOMPLEX" ]]; then
    echo 0
  else
    echo 1
  fi
}

for date_name in "${date_dirs[@]}"; do
  source_date_dir="$slc_dir/$date_name"
  output_date_dir="$burst_dir/$date_name"

  if [[ -e "$output_date_dir" ]]; then
    echo "ERROR: output directory already exists: ${output_date_dir}" >&2
    echo "Use a new task root, or inspect the existing result before retrying." >&2
    exit 1
  fi

  mkdir "$output_date_dir"
  cd "$output_date_dir"

  for index in "${!selected_swaths[@]}"; do
    swath_name=${selected_swaths[$index]}
    bn_start=${burst_pairs[$((index * 2))]}
    bn_end=${burst_pairs[$((index * 2 + 1))]}
    source_par="$source_date_dir/${date_name}.${swath_name}_${pol}.slc.par"

    if [[ ! "$bn_start" =~ ^[0-9]+$ || ! "$bn_end" =~ ^[0-9]+$ ]]; then
      echo "ERROR: burst range for ${swath_name} must be integers: ${bn_start} ${bn_end}" >&2
      exit 1
    fi
    if (( bn_start < 1 || bn_end < bn_start )); then
      echo "ERROR: invalid burst range for ${swath_name}: ${bn_start} ${bn_end}" >&2
      exit 1
    fi
    if [[ ! -f "$source_par" ]]; then
      echo "ERROR: selected swath product is missing: ${source_par}" >&2
      exit 1
    fi

    input_tab="${date_name}.${swath_name}.input.SLC_tab"
    output_tab="${date_name}.${swath_name}.output.SLC_tab"
    cp "$source_date_dir/SLC_tab" "$input_tab"
    cp "$source_date_dir/SLC_tab" "$output_tab"
    sed -i "s#${date_name}#${source_date_dir}/${date_name}#g" "$input_tab"
    filter_tab_to_swaths "$input_tab" "$swath_name"
    filter_tab_to_swaths "$output_tab" "$swath_name"

    printf "%s %s\n" "$bn_start" "$bn_end" > BURST_tab
    echo "SLC_copy_S1_TOPS ${input_tab} ${output_tab} BURST_tab"
    SLC_copy_S1_TOPS "$input_tab" "$output_tab" BURST_tab

    source_slc="${date_name}.${swath_name}_${pol}.slc"
    width=$(awk '/range_samples:/ {print $2; exit}' "$source_par")
    if [[ -z "$width" ]]; then
      echo "ERROR: range_samples is missing from ${source_par}" >&2
      exit 1
    fi
    format=$(slc_format_code "$source_par")
    rasSLC "$source_slc" "$width" - - 50 10 - - - "$format" - "${source_slc}.bmp"
  done

  cp "$source_date_dir/SLC_tab" SLC_tab2
  filter_tab_to_swaths SLC_tab2 "${selected_swaths[@]}"
  SLC_mosaic_S1_TOPS SLC_tab2 "${date_name}.slc" "${date_name}.slc.par" 10 2 1

  mosaic_width=$(awk '/range_samples:/ {print $2; exit}' "${date_name}.slc.par")
  if [[ -z "$mosaic_width" ]]; then
    echo "ERROR: range_samples is missing from ${date_name}.slc.par" >&2
    exit 1
  fi
  mosaic_format=$(slc_format_code "${date_name}.slc.par")
  rasSLC "${date_name}.slc" "$mosaic_width" - - 50 10 - - - "$mosaic_format" - "${date_name}.slc.bmp"
done
