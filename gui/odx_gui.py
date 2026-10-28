#!/usr/bin/env python3
"""
ODX (OpenDroneMap X) - Auto-Manager z Wykrywaniem GCP
Program startowy wzorowany 1:1 na ~/ODM/gui/odm_gui.py, dostosowany do ODX 3.8.x.

ODX to szybszy fork OpenDroneMap (obraz webodm/odx). Uruchamiamy go w Dockerze,
montując katalog projektu jako /datasets - tak samo jak ODM, ale z opcjami ODX:
--no-gpu, --matcher-type, --sfm-algorithm, --3d-tiles, --gltf, --pc-copc,
--orthophoto-kmz, --dem-resolution, --skip-report itd.

UWAGA: --build-overviews jest w ODX przestarzałe (wywołuje ostrzeżenie i włącza
--cog). Dlatego nie ma go w interfejsie - piramidy obrazu buduje --cog.
"""

import io
import json
import os
import shlex
import time
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "ODX - Auto-Manager z Wykrywaniem GCP (OpenDroneMap X)"
ODX_IMAGE = os.environ.get("ODX_IMAGE", "webodm/odx:latest")
ODX_GPU_IMAGE = os.environ.get("ODX_GPU_IMAGE", "webodm/odx:gpu")
IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    _config_root = Path(os.environ.get("APPDATA", str(Path.home())))
else:
    _config_root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))

CONFIG_DIR = _config_root / "odx-gui"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "error.log"
RUN_SCRIPT = CONFIG_DIR / ("run_tmp.bat" if IS_WINDOWS else "run_tmp.sh")
WORK_DIR = CONFIG_DIR / "work"

# ODX 3.8.x: modules/context.py -> supported_extensions
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp",
              ".raw", ".dng", ".nef", ".jxl"}
VIDEO_EXTS = {".mp4", ".mov", ".lrv", ".ts"}
SIDECAR_EXTS = {".srt"}
GCP_SKIP = {"requirements.txt", "options.json", "version.txt",
            "images.json", "cameras.json", "log.json"}
QUALITIES = ["lowest", "low", "medium", "high", "ultra"]
MATCHERS = ["auto", "flann", "bow", "bruteforce", "hamming"]
SFM_ALGOS = ["incremental", "triangulation"]
FEATURE_TYPES = ["dspsift", "sift", "akaze", "hahog", "orb"]
CAMERA_LENSES = ["auto", "perspective", "brown", "fisheye",
                 "fisheye_opencv", "spherical", "equirectangular", "dual"]
ORTHO_COMPRESSION = ["DEFLATE", "JPEG", "LZW", "PACKBITS", "LZMA", "NONE"]
REPORT_UNITS = ["m", "ft", "US survey foot"]
END_STAGES = ["odm_postprocess", "odm_report", "odm_orthophoto", "odm_dem",
              "odm_georeferencing", "mvs_texturing", "odm_meshing",
              "odm_filterpoints", "openmvs", "opensfm", "merge", "split"]

# kolory z oryginału (RGBToColor)
C_BLUE = "#005A9E"
C_GREEN = "#107C41"
C_BLUE2 = "#2B579A"
C_DARKRED = "#A80000"
C_GRAY1 = "#777777"
C_GRAY2 = "#555555"

# Czcionka jak w systemie/oknie pulpitu: Noto Sans 10 (zamiast DejaVu Sans 9).
UI_FAMILY = "Segoe UI" if IS_WINDOWS else "Noto Sans"
UI_SIZE = 10
MONO_FAMILY = "Consolas" if IS_WINDOWS else "DejaVu Sans Mono"
MONO_SIZE = 10

# ODX jest ok. 25-35% szybszy od ODM; wartości celowo lekko zachowawcze.
SEC_PER_IMG = {"lowest": 6, "low": 9, "medium": 22, "high": 60, "ultra": 135}


# ----------------------------------------------------------------------
#  Pomocnicze funkcje plikowe (odpowiedniki z unit1.pas)
# ----------------------------------------------------------------------
def log_exception() -> None:
    """Zapisuje traceback do error.log - okno GUI bywa bez konsoli."""
    try:
        import traceback
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with io.open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write("\n=== %s ===\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            fh.write(traceback.format_exc())
    except OSError:
        pass


def normalize_path(p: str) -> str:
    p = os.path.expanduser(os.path.expandvars(p.strip()))
    if not p:
        return ""
    return os.path.normpath(p)


def project_folder(f: str) -> str:
    """Jeśli wskazano katalog 'images', projektem jest jego katalog nadrzędny."""
    if not f:
        return f
    if os.path.basename(f.rstrip(os.sep)).lower() == "images":
        parent = os.path.dirname(f.rstrip(os.sep))
        if parent:
            return parent
    return f


def is_image_ext(ext: str) -> bool:
    return ext.lower() in IMAGE_EXTS


def is_video_ext(ext: str) -> bool:
    return ext.lower() in VIDEO_EXTS


def collect_images(directory: str) -> list[str]:
    out = []
    try:
        for name in sorted(os.listdir(directory)):
            full = os.path.join(directory, name)
            if os.path.isfile(full) and is_image_ext(os.path.splitext(name)[1]):
                out.append(full)
    except OSError:
        pass
    return out


def collect_videos(directory: str) -> list[str]:
    out = []
    try:
        for name in sorted(os.listdir(directory)):
            full = os.path.join(directory, name)
            if os.path.isfile(full) and is_video_ext(os.path.splitext(name)[1]):
                out.append(full)
    except OSError:
        pass
    return out


def collect_sidecars(directory: str) -> list[str]:
    """Pliki .srt z GPS dla wideo (muszą leżeć obok filmów)."""
    out = []
    try:
        for name in sorted(os.listdir(directory)):
            full = os.path.join(directory, name)
            if os.path.isfile(full) and os.path.splitext(name)[1].lower() in SIDECAR_EXTS:
                out.append(full)
    except OSError:
        pass
    return out


def scan_assets(folder: str) -> tuple[int, int, bool]:
    """Zwraca (zdjęcia, filmy, czy_w_podfolderze_images)."""
    if not folder or not os.path.isdir(folder):
        return 0, 0, False
    sub = os.path.join(folder, "images")
    imgs, vids = collect_images(sub), collect_videos(sub)
    if imgs or vids:
        return len(imgs), len(vids), True
    return len(collect_images(folder)), len(collect_videos(folder)), False


def is_alnum_no_colon(s: str) -> bool:
    return bool(s) and all(c.isalnum() or c == "_" for c in s)


def read_text_lines(fn: str) -> list[str]:
    try:
        data = Path(fn).read_bytes()
    except OSError:
        return []
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
        try:
            return data.decode(enc).splitlines()
        except UnicodeDecodeError:
            continue
    return []


def detect_gcp(folder: str) -> tuple[str, int, str]:
    """Odpowiednik DetectGCP: szuka pliku fotopunktów i układu współrzędnych."""
    if not folder or not os.path.isdir(folder):
        return "", 0, ""

    candidates = [
        os.path.join(folder, "gcp_list.txt"),
        os.path.join(folder, "gcp.txt"),
    ]
    try:
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            if os.path.isfile(full) and name.lower().endswith(".txt"):
                candidates.append(full)
    except OSError:
        pass

    seen = set()
    for fn in candidates:
        key = fn.lower()
        if key in seen:
            continue
        seen.add(key)
        if not os.path.isfile(fn):
            continue
        if os.path.basename(fn).lower() in GCP_SKIP:
            continue

        lines = [s.strip() for s in read_text_lines(fn)]
        lines = [s for s in lines if s and not s.startswith("#")]
        if len(lines) < 2:
            continue

        first = lines[0]
        low = first.lower()
        if "epsg" in low or "+" in first or "wgs" in low or is_alnum_no_colon(first):
            return fn, len(lines) - 1, first

    return "", 0, ""


# ----------------------------------------------------------------------
#  Docker / ODX
# ----------------------------------------------------------------------
def docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=20,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def nvidia_available() -> bool:
    """Czy host widzi GPU NVIDIA (wymagane dla obrazu :gpu i --gpus all)."""
    if not shutil.which("nvidia-smi"):
        return False
    try:
        r = subprocess.run(["nvidia-smi", "-L"], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=8, text=True)
        return r.returncode == 0 and "GPU" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def split_extra_args(text: str) -> list[str]:
    """Dzieli dodatkowe argumenty. Na Windows nie zjada backslashy ze ścieżek."""
    if not text.strip():
        return []
    if not IS_WINDOWS:
        return shlex.split(text)
    parts = shlex.split(text, posix=False)
    out = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
            part = part[1:-1]
        out.append(part)
    return out


def format_command(argv: list[str]) -> str:
    """Czytelny podgląd komendy: cmd.exe na Windows, POSIX sh gdzie indziej."""
    if IS_WINDOWS:
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


# Wykrywanie instalacji ODX ma się zdarzyć RAZ (przy pierwszym uruchomieniu).
# Wynik ląduje w config.json, a kolejne starty czytają tylko tę wartość.
_ODX_CACHE = {"value": "", "scanned": False}


def _odx_dir_from_package() -> str:
    """Cache zapisany przez _srodowisko.bat obok startera (odx_path.txt)."""
    try:
        f = Path(__file__).resolve().parent.parent / "odx_path.txt"
        return f.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _odx_dir_from_config() -> str:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        v = data.get("odx_dir", "")
        return v if isinstance(v, str) else ""
    except (OSError, ValueError):
        return ""


def detect_odx_dir(force: bool = False) -> str:
    """Zwraca folder natywnego ODX (z run.bat). Skanuje tylko raz na proces."""
    if not IS_WINDOWS:
        return ""
    if _ODX_CACHE["scanned"] and not force:
        return _ODX_CACHE["value"]

    if not force:
        saved = _odx_dir_from_package() or _odx_dir_from_config()
        if saved and os.path.isfile(os.path.join(saved, "run.bat")):
            _ODX_CACHE.update(value=os.path.normpath(saved), scanned=True)
            return _ODX_CACHE["value"]

    cands = []
    for key in ("ODX_HOME", "ODX_DIR"):
        v = os.environ.get(key)
        if v:
            cands.append(v)
    cands += [
        r"C:\ODX",
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "ODX"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "ODX"),
        os.path.join(os.environ.get("LOCALAPPDATA", str(Path.home())), "Programs", "ODX"),
        os.path.join(str(Path.home()), "ODX"),
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "ODX"),
        r"D:\ODX",
    ]
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key in (
                "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"
                "{443998BA-9F8F-4A69-9A96-0D8FBC8C6394}_is1",
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ODX_is1",
            ):
                for view in (0, getattr(winreg, "KEY_WOW64_32KEY", 0)):
                    try:
                        with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as k:
                            loc, _ = winreg.QueryValueEx(k, "InstallLocation")
                            if loc:
                                cands.append(loc)
                    except OSError:
                        pass
    except ImportError:
        pass
    found = ""
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "run.bat")):
            found = os.path.normpath(c)
            break
    if not found:
        found = os.path.normpath(cands[0]) if cands else r"C:\ODX"
    _ODX_CACHE.update(value=found, scanned=True)
    return found


def redetect_odx_dir() -> str:
    """Wymusza ponowne skanowanie (przycisk 'Wykryj ODX ponownie')."""
    _ODX_CACHE.update(value="", scanned=False)
    return detect_odx_dir(force=True)


# ----------------------------------------------------------------------
#  Zakladka "Wiecej opcji ODX" - deklaratywne mapowanie na flagi ODX
# ----------------------------------------------------------------------
# klucz interfejsu -> flaga ODX (przelaczniki bez wartosci)
BOOL_FLAGS = [
    ("opt_png", "--orthophoto-png"),
    ("opt_tiles", "--tiles"),
    ("opt_cutline", "--orthophoto-cutline"),
    ("opt_no_tiled", "--orthophoto-no-tiled"),
    ("skip_ortho", "--skip-orthophoto"),
    ("pc_las", "--pc-las"),
    ("pc_csv", "--pc-csv"),
    ("pc_ept", "--pc-ept"),
    ("dem_euclidean", "--dem-euclidean-map"),
    ("force_gps", "--force-gps"),
    ("ignore_gsd", "--ignore-gsd"),
    ("fixed_camera", "--use-fixed-camera-params"),
    ("rolling_shutter", "--rolling-shutter"),
    ("sky_removal", "--sky-removal"),
    ("bg_removal", "--bg-removal"),
    # --- georeferencja / fotopunkty / SfM ---
    ("use_exif", "--use-exif"),
    ("sfm_no_partial", "--sfm-no-partial"),
    ("hybrid_ba", "--use-hybrid-bundle-adjustment"),
    ("sm_no_align", "--sm-no-align"),
    # --- chmura / tekstury ---
    ("pc_skip_geom", "--pc-skip-geometric"),
    ("tex_skip_seam", "--texturing-skip-global-seam-leveling"),
    ("tex_keep_unseen", "--texturing-keep-unseen-faces"),
    ("tex_single_mat", "--texturing-single-material"),
    # --- multispektralne ---
    ("skip_band_align", "--skip-band-alignment"),
]

# klucz -> (flaga, wartosc domyslna ODX, sposob porownania)
VALUE_OPTS = [
    ("ortho_compression", "--orthophoto-compression", "DEFLATE", "text"),
    ("crop", "--crop", "3", "num"),
    ("pc_filter", "--pc-filter", "5", "num"),
    ("pc_sample", "--pc-sample", "0", "num"),
    ("dem_decimation", "--dem-decimation", "1", "num"),
    ("mesh_size", "--mesh-size", "200000", "num"),
    ("mesh_octree", "--mesh-octree-depth", "11", "num"),
    ("min_features", "--min-num-features", "10000", "num"),
    ("feature_type", "--feature-type", "dspsift", "text"),
    ("gps_accuracy", "--gps-accuracy", "3", "num"),
    ("camera_lens", "--camera-lens", "auto", "text"),
    ("video_limit", "--video-limit", "500", "num"),
    ("video_res", "--video-resolution", "4000", "num"),
    ("report_units", "--report-units", "m", "text"),
    ("end_with", "--end-with", "odm_postprocess", "text"),
    # --- georeferencja / fotopunkty ---
    ("boundary", "--boundary", "", "text"),
    ("geo", "--geo", "", "text"),
    ("align", "--align", "", "text"),
    ("copy_to", "--copy-to", "", "text"),
    ("matcher_neighbors", "--matcher-neighbors", "0", "num"),
    ("gps_z_offset", "--gps-z-offset", "0", "num"),
    ("radiometric", "--radiometric-calibration", "none", "text"),
    ("primary_band", "--primary-band", "", "text"),
    # --- duze zbiory / DEM ---
    ("split", "--split", "999999", "num"),
    ("split_overlap", "--split-overlap", "150", "num"),
    ("smrf_window", "--smrf-window", "18", "num"),
    ("dem_gapfill", "--dem-gapfill-steps", "3", "num"),
]

# opcje sensowne tylko z ortofoto / gesta chmura / modelem 3D
ORTHO_KEYS = {"opt_png", "opt_tiles", "opt_cutline", "opt_no_tiled",
              "ortho_compression", "crop"}
DENSE_KEYS = {"pc_las", "pc_csv", "pc_ept", "pc_filter", "pc_sample",
              "pc_skip_geom"}
MODEL_KEYS = {"mesh_size", "mesh_octree", "tex_skip_seam",
              "tex_keep_unseen", "tex_single_mat"}
DEM_KEYS = {"dem_decimation", "dem_euclidean", "smrf_window",
            "dem_gapfill"}
MORE_VALUE_DEFAULTS = {k: d for k, _, d, _ in VALUE_OPTS}

# wysokosc zawartosci przewijanej zakladki "Wiecej opcji ODX"
MORE_TAB_HEIGHT = 1304

RADIOMETRIC = ["none", "camera", "camera+sun"]


def build_command(project_dir: str, gcp_path: str, opts: dict) -> list[str]:
    """Buduje komendę: natywny run.bat na Windows, kontener Docker na Linuksie."""
    if IS_WINDOWS:
        odx_dir = opts.get("odx_dir") or detect_odx_dir()
        # run.py sklada sciezke jako --project-path + <nazwa>, tak samo
        # jak w natywnej instalacji na Linuksie (wczesniej podawano
        # pelna sciezke, co dzialalo tylko przypadkiem).
        project_dir = project_dir.rstrip("\\/")
        _parent = os.path.dirname(project_dir) or project_dir
        _name = os.path.basename(project_dir)
        argv = [os.path.join(odx_dir, "run.bat"), _name,
                "--project-path", _parent]
    else:
        project_dir = project_dir.rstrip(os.sep)
        parent = os.path.dirname(project_dir) or "/"
        name = os.path.basename(project_dir)
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        use_gpu = bool(opts["use_gpu"])
        image = ODX_GPU_IMAGE if use_gpu else ODX_IMAGE
        argv = ["docker", "run", "--rm", "-i"]
        if use_gpu:
            argv += ["--gpus", "all"]
        argv += [
            "--user", f"{os.getuid()}:{os.getgid()}",
            "-w", "/work",
            "-e", "HOME=/tmp",
            "-e", "TMPDIR=/work",
            "-e", "PYTHONUTF8=1",
            "-v", f"{WORK_DIR}:/work",
            "-v", f"{parent}:/datasets",
            image,
            "--project-path", "/datasets",
            name,
        ]

    if opts["rerun"]:
        argv += ["--rerun-all"]
    argv += [
        "--feature-quality", opts["feat_qual"],
        "--pc-quality", opts["pc_qual"],
        "--max-concurrency", str(opts["threads"]),
    ]
    if opts["dsm"] and not opts["fast_ortho"]:
        argv += ["--dsm"]
    if opts["dtm"] and not opts["fast_ortho"]:
        argv += ["--dtm"]
    if opts["skip_3d"] and not opts["use_3dmesh"] and not opts["fast_ortho"]:
        argv += ["--skip-3dmodel"]
    if opts["cog"]:
        argv += ["--cog"]
    if opts["auto_bound"]:
        argv += ["--auto-boundary"]
    if opts["fast_ortho"] and not opts["use_3dmesh"]:
        argv += ["--fast-orthophoto"]
    if opts["use_3dmesh"] and not opts["fast_ortho"]:
        argv += ["--use-3dmesh"]
    if opts["opt_disk"]:
        argv += ["--optimize-disk-space"]

    if opts["no_gpu"] and not (not IS_WINDOWS and opts["use_gpu"]):
        argv += ["--no-gpu"]
    if opts["matcher"] != "auto":
        argv += ["--matcher-type", opts["matcher"]]
    if opts["sfm"] != "incremental":
        argv += ["--sfm-algorithm", opts["sfm"]]
    if (opts["dsm"] or opts["dtm"]) and not opts["fast_ortho"]:
        try:
            dem_value = float(opts["dem_res"])
        except (TypeError, ValueError):
            dem_value = 5.0
        if dem_value != 5.0:
            argv += ["--dem-resolution", opts["dem_res"]]

    model_ok = not (opts["skip_3d"] or opts["fast_ortho"])
    dense_ok = not opts["fast_ortho"]
    if opts["gltf"] and model_ok:
        argv += ["--gltf"]
    if opts["three_d_tiles"] and model_ok:
        argv += ["--3d-tiles"]
    if opts["pc_classify"] and dense_ok:
        argv += ["--pc-classify"]
    if opts["pc_copc"] and dense_ok:
        argv += ["--pc-copc"]
    if opts["kmz"]:
        argv += ["--orthophoto-kmz"]
    if not opts["report"]:
        argv += ["--skip-report"]
    if gcp_path:
        argv += ["--gcp", gcp_path]

    # ---- zakladka "Wiecej opcji ODX" ----
    demo = bool(opts.get("dsm") or opts.get("dtm"))
    ortho_on = not opts.get("skip_ortho")
    allowed = {"ORTHO": ortho_on, "DENSE": dense_ok, "MODEL": model_ok,
               "DEM": demo}
    for key, flag in BOOL_FLAGS:
        group = ("ORTHO" if key in ORTHO_KEYS else
                 "DENSE" if key in DENSE_KEYS else
                 "MODEL" if key in MODEL_KEYS else
                 "DEM" if key in DEM_KEYS else "")
        if group and not allowed[group]:
            continue
        if opts.get(key):
            argv.append(flag)

    for key, flag, default, mode in VALUE_OPTS:
        group = ("ORTHO" if key in ORTHO_KEYS else
                 "DENSE" if key in DENSE_KEYS else
                 "MODEL" if key in MODEL_KEYS else
                 "DEM" if key in DEM_KEYS else "")
        if group and not allowed[group]:
            continue
        raw = str(opts.get(key, default)).strip()
        if not raw:
            continue
        if mode == "num":
            try:
                if float(raw.replace(",", ".")) == float(default):
                    continue
            except ValueError:
                continue
        elif raw == default:
            continue
        argv += [flag, raw]

    argv += ["--orthophoto-resolution", opts["ortho_res"]]
    if opts.get("extra_args"):
        argv += opts["extra_args"]
    return argv


TERMINALS = {
    "x-terminal-emulator": ["x-terminal-emulator", "-e"],
    "konsole": ["konsole", "-e"],
    "xfce4-terminal": ["xfce4-terminal", "-x"],
    "lxterminal": ["lxterminal", "-e"],
    "mate-terminal": ["mate-terminal", "-x"],
    "qterminal": ["qterminal", "-e"],
    "gnome-terminal": ["gnome-terminal", "--"],
    "xterm": ["xterm", "-e"],
}


def pick_terminal() -> list[str]:
    for exe, argv in TERMINALS.items():
        if shutil.which(exe):
            return argv
    return []


def make_posix_script(argv: list[str], folder: str, project_name: str) -> str:
    return f"""#!/usr/bin/env bash
# wygenerowane przez ODX Auto-Manager
set -u
echo "=== ODX (OpenDroneMap X): {project_name} ==="
echo "Katalog projektu: {folder}"
echo
printf '%s\\n' {shlex.quote(shlex.join(argv))}
echo
CMD={shlex.quote(shlex.join(argv))}

# Blokada uśpienia: bez tego laptop może zasnąć w środku wielogodzinnego przebiegu.
if command -v systemd-inhibit >/dev/null 2>&1 \
   && systemd-inhibit --what=idle:sleep --why="probe" --mode=block true >/dev/null 2>&1; then
  echo "\U0001F512 Blokada uśpienia aktywna na czas przetwarzania."
  systemd-inhibit --what=idle:sleep --why="ODX: {project_name}" \
      --mode=block bash -c "$CMD"
else
  echo "\u26A0 Nie udało się zablokować uśpienia (systemd-inhibit niedostępny)."
  echo "   Zablokuj je ręcznie - inaczej przebieg może zostać przerwany."
  bash -c "$CMD"
fi
rc=$?
echo
if [ $rc -eq 0 ]; then
  echo "✅ Zakończono pomyślnie. Wyniki w: {folder}"
else
  echo "❌ ODX zakończył się błędem (kod $rc)."
fi
echo
read -n 1 -r -p "Naciśnij dowolny klawisz, aby zamknąć..." _
echo
"""


def _quote_win_arg(arg: str) -> str:
    """Cytuje argument dla cmd.exe także przy znakach & | < > ^."""
    if arg == "":
        return '""'
    if any(ch in arg for ch in ' \t"&|<>^'):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def make_windows_script(argv: list[str], folder: str, project_name: str) -> str:
    """Skrypt .bat dla cmd.exe. Treść ASCII + chcp 65001 (polskie ścieżki)."""
    exec_cmd = " ".join(_quote_win_arg(a) for a in argv).replace("%", "%%")
    if argv and argv[0].lower().endswith((".bat", ".cmd")):
        exec_cmd = "call " + exec_cmd
    safe_name = "".join(c for c in project_name if c not in '&|<>^"%')
    folder_disp = folder.replace("%", "%%").replace('"', "'")
    return f"""@echo off
chcp 65001 >nul
title ODX - {safe_name}
echo === ODX (OpenDroneMap X): {safe_name} ===
echo Katalog projektu: "{folder_disp}"
echo.
echo {exec_cmd}
echo.
{exec_cmd}
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" goto odx_ok
echo [BLAD] ODX zakonczyl sie bledem (kod %RC%).
goto odx_end
:odx_ok
echo [OK] Zakonczono pomyslnie.
echo Wyniki w: "{folder_disp}"
:odx_end
echo.
pause
"""


# ----------------------------------------------------------------------
#  GUI
# ----------------------------------------------------------------------
class ODXForm(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        # Na mniejszych ekranach okno skraca się, a formularz można przewijać.
        screen_h = self.winfo_screenheight()
        win_h = min(968, max(620, screen_h - 100))
        self.geometry(f"874x{win_h}")
        self.minsize(874, 620)
        self.resizable(True, True)
        self.configure(bg="#f0f0f0")
        self._updating = False
        self._fast_block_prev = None
        self._docker_ok = True if IS_WINDOWS else docker_available()
        self._nvidia = nvidia_available()
        self.cfg = self.load_config()
        # Windows: wykrycie ODX tylko raz, potem wynik z config.json
        self._odx_dir = detect_odx_dir() if IS_WINDOWS else ""
        if len(sys.argv) > 1 and os.path.isdir(os.path.expanduser(sys.argv[1])):
            self.cfg["last_folder"] = normalize_path(sys.argv[1])

        self.setup_style()
        self.build_ui()
        self.restore_settings()
        self.assign_events()
        self.update_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- wygląd ----------------
    def setup_style(self) -> None:
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        base = (UI_FAMILY, UI_SIZE)
        st.configure("TLabel", font=base, background="#f0f0f0")
        st.configure("TEntry", font=base)
        st.configure("TCombobox", font=base)
        st.configure("TCheckbutton", font=base, background="#f0f0f0")
        st.configure("TLabelframe", background="#f0f0f0")
        st.configure("TLabelframe.Label", font=base, foreground="#000000",
                     background="#f0f0f0")
        st.configure("TButton", font=base)
        st.configure("TNotebook", background="#f0f0f0")
        st.configure("TNotebook.Tab", font=(UI_FAMILY, UI_SIZE, "bold"), padding=(12, 4))

    def mk_group(self, parent, text: str, x: int, y: int, w: int, h: int) -> ttk.LabelFrame:
        g = ttk.LabelFrame(parent, text=text, labelanchor="nw")
        g.place(x=x, y=y, width=w, height=h)
        return g

    def mk_label(self, parent, x, y, text, bold=False, color=None, size=UI_SIZE,
                 font=UI_FAMILY, wrap=0) -> tk.Label:
        style = (font, size, "bold") if bold else (font, size)
        lbl = tk.Label(parent, text=text, font=style, bg="#f0f0f0",
                       fg=color or "#000000", anchor="w", justify="left")
        if wrap:
            lbl.configure(wraplength=wrap)
        lbl.place(x=x, y=y)
        return lbl

    def mk_check(self, parent, x, y, text, checked, width=None) -> tk.Checkbutton:
        var = tk.BooleanVar(value=checked)
        chk = tk.Checkbutton(parent, text=text, variable=var, bg="#f0f0f0",
                             activebackground="#f0f0f0", font=(UI_FAMILY, UI_SIZE),
                             anchor="w", padx=1)
        if width:
            chk.configure(wraplength=width, justify="left")
        chk.place(x=x, y=y)
        chk.var = var
        return chk

    # ---------------- budowa interfejsu ----------------
    def build_ui(self) -> None:
        # Przewijany kontener: formularz ma stałą wysokość 968 px, ale na
        # ekranie 768p/900p dolne sekcje pozostają dostępne przez scroll.
        self.canvas = tk.Canvas(self, bg="#f0f0f0", highlightthickness=0,
                                yscrollincrement=28)
        self.vbar = ttk.Scrollbar(self, orient="vertical",
                                  command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        self.rootframe = tk.Frame(self.canvas, bg="#f0f0f0")
        self._canvas_win = self.canvas.create_window(
            (0, 0), window=self.rootframe, anchor="nw", width=860, height=968)
        self.rootframe.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._sync_scrollbar)
        self.after(300, self._sync_scrollbar)
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)

        self.nb = ttk.Notebook(self.rootframe)
        self.nb.place(x=10, y=8, width=840, height=670)

        self.tab_main = tk.Frame(self.nb, bg="#f0f0f0")
        self.tab_adv = tk.Frame(self.nb, bg="#f0f0f0")
        self.tab_more = tk.Frame(self.nb, bg="#f0f0f0")
        self.nb.add(self.tab_main, text="  Projekt i jakość  ")
        self.nb.add(self.tab_adv, text="  Opcje ODX / zaawansowane  ")
        self.nb.add(self.tab_more, text="  Więcej opcji ODX  ")

        self.build_main_tab()
        self.build_adv_tab()
        self.build_more_tab()

        # ---- szacowany czas ----
        self.g_time = self.mk_group(self.rootframe, " Szacowany Czas Obliczeń ", 10, 686, 840, 70)
        self.lbl_time = self.mk_label(self.g_time, 10, 12,
                                      "Szacowany czas: -- min",
                                      bold=True, color=C_BLUE2, size=UI_SIZE - 1)
        self.btn_night = tk.Button(
            self.g_time, text="WYSOKA JAKOŚĆ",
            font=(UI_FAMILY, 9, "bold"), bg=C_BLUE2, fg="white",
            activebackground="#1f4278", activeforeground="white",
            relief="flat", bd=0, cursor="hand2",
            command=self.apply_night_preset)
        self.btn_night.place(x=470, y=6, width=170, height=32)

        # preset szybki: ortofoto z rzadkiej chmury, ~3 cm/px, bez raportu
        self.btn_express = tk.Button(
            self.g_time, text="EKSPRES ORTO",
            font=(UI_FAMILY, 9, "bold"), bg=C_GREEN, fg="white",
            activebackground="#0c5f32", activeforeground="white",
            relief="flat", bd=0, cursor="hand2",
            command=self.apply_express_preset)
        self.btn_express.place(x=648, y=6, width=164, height=32)

        # ---- podgląd komendy ----
        self.g_cmd = self.mk_group(self.rootframe, " Podgląd Wygenerowanej Komendy ", 10, 762, 840, 138)
        self.memo = tk.Text(self.g_cmd, font=(MONO_FAMILY, MONO_SIZE), wrap="word",
                            bg="white", relief="solid", bd=1, height=5)
        self.memo.place(x=10, y=18, width=798, height=88)
        # pionowy suwak: długa komenda (dużo opcji) bywa dłuższa niż 4 linie
        self.memo_sb = ttk.Scrollbar(self.g_cmd, orient="vertical",
                                     command=self.memo.yview)
        self.memo_sb.place(x=809, y=18, width=14, height=88)
        self.memo.configure(state="disabled", yscrollcommand=self.memo_sb.set)

        # ---- przycisk start ----
        self.btn_run = tk.Button(
            self.rootframe, text="PRZYGOTUJ FOLDER I URUCHOM ODX",
            font=(UI_FAMILY, 11, "bold"), bg=C_GREEN, fg="white",
            activebackground="#0c5f32", activeforeground="white",
            relief="flat", bd=0, command=self.btn_run_click, cursor="hand2")
        self.btn_run.place(x=15, y=908, width=830, height=50)

    def build_main_tab(self) -> None:
        t = self.tab_main

        # ---- sekcja: wybór folderu ----
        self.g_paths = self.mk_group(t, " Wskaż Katalog ze Zdjęciami (Projekt) ",
                                     6, 2, 824, 154)
        self.mk_label(self.g_paths, 10, 24, "Folder projektu:")
        self.edt_folder = ttk.Entry(self.g_paths, font=(UI_FAMILY, UI_SIZE))
        self.edt_folder.place(x=124, y=20, width=546, height=26)
        self.btn_browse = ttk.Button(self.g_paths, text="Przeglądaj...",
                                     command=self.btn_browse_click)
        self.btn_browse.place(x=678, y=17, width=134, height=30)

        self.lbl_photo = self.mk_label(self.g_paths, 10, 52, " Status zdjęć: --",
                                       bold=True, color=C_BLUE)
        self.lbl_video = self.mk_label(self.g_paths, 10, 75,
                                       " Status wideo: brak filmów",
                                       color=C_GRAY1)
        self.lbl_gcp = self.mk_label(
            self.g_paths, 10, 100, " Status GCP: Brak pliku gcp_list.txt",
            bold=True, color=C_GRAY1)

        # ---- sekcja: jakość / wątki / rozdzielczość ----
        self.g_opts = self.mk_group(t, " Jakość, Wątki i Rozdzielczość Rastrowa ",
                                    6, 162, 824, 178)
        self.mk_label(self.g_opts, 10, 28,
                      "Rozdzielczość ortofotomapy (--orthophoto-resolution cm/px):")
        self.edt_ortho = ttk.Entry(self.g_opts, font=(UI_FAMILY, UI_SIZE))
        self.edt_ortho.insert(0, "2.0")
        self.edt_ortho.place(x=470, y=24, width=100, height=26)

        self.mk_label(self.g_opts, 10, 58,
                      "Jakość detekcji punktów (--feature-quality):")
        self.cmb_feat = ttk.Combobox(self.g_opts, values=QUALITIES, state="readonly",
                                     font=(UI_FAMILY, UI_SIZE))
        self.cmb_feat.set("medium")
        self.cmb_feat.place(x=470, y=54, width=120, height=26)

        self.mk_label(self.g_opts, 10, 88,
                      "Gęstość chmury punktów (--pc-quality):")
        self.cmb_pc = ttk.Combobox(self.g_opts, values=QUALITIES, state="readonly",
                                   font=(UI_FAMILY, UI_SIZE))
        self.cmb_pc.set("medium")
        self.cmb_pc.place(x=470, y=84, width=120, height=26)

        self.mk_label(self.g_opts, 10, 118,
                      "Maksymalna liczba wątków CPU (--max-concurrency):")
        self.edt_threads = ttk.Entry(self.g_opts, font=(UI_FAMILY, UI_SIZE))
        self.edt_threads.insert(0, "4")
        self.edt_threads.place(x=470, y=114, width=100, height=26)

        # ---- sekcja: flagi ----
        self.g_flags = self.mk_group(t, " Opcje Przetwarzania i Integracja QGIS ",
                                     6, 346, 824, 286)

        def chk(parent, x, y, text, checked):
            return self.mk_check(parent, x, y, text, checked)

        self.chk_dsm = chk(self.g_flags, 10, 26,
                           "NMPT / Model Pokrycia Terenu (--dsm)", True)
        self.chk_dtm = chk(self.g_flags, 410, 26,
                           "NPMT / Model Terenu Gruntu (--dtm)", True)
        self.chk_rerun = chk(self.g_flags, 10, 56,
                             "Czyszczenie przed startem (--rerun-all)", True)
        self.chk_optdisk = chk(self.g_flags, 410, 56,
                               "Kasowanie plików roboczych (--optimize-disk-space)", False)
        self.chk_skip3d = chk(self.g_flags, 10, 86,
                              "Szybszy bieg: Pomiń Mesh 3D (--skip-3dmodel)", False)
        self.chk_cog = chk(self.g_flags, 410, 86,
                           "Płynny QGIS: Cloud-Optimized GeoTIFF (--cog)", True)
        self.chk_autobound = chk(self.g_flags, 10, 116,
                                 "Auto-przycinanie krawędzi (--auto-boundary)", True)
        self.chk_fastortho = chk(self.g_flags, 410, 116,
                                 "Szybka ortofotomapa ekspresowa (--fast-orthophoto)", False)
        self.chk_use3dmesh = chk(self.g_flags, 10, 146,
                                 "Orto z siatki 3D - pionowe ściany (--use-3dmesh)", False)

        self.mk_label(
            self.g_flags, 10, 186,
            "Uwaga: ODX nie ma już opcji --build-overviews (przestarzała) - piramidy obrazu "
            "buduje automatycznie --cog.",
            color=C_GRAY2, size=8)
        self.mk_label(
            self.g_flags, 10, 210,
            "   --fast-orthophoto wyłącza gęstą chmurę, model 3D oraz NMPT/NPMT "
            "(tylko ortofoto). --use-3dmesh wyklucza --fast-orthophoto i --skip-3dmodel.",
            color=C_GRAY2, size=8)

        self.lbl_hint = self.mk_label(
            self.g_flags, 10, 238,
            "Wskazówka: przy 7,6 GB RAM pozostaw --max-concurrency 4 i jakość medium.",
            color=C_BLUE, size=8)

    def build_adv_tab(self) -> None:
        t = self.tab_adv

        # ---- GPU / dopasowanie / SfM ----
        self.g_gpu = self.mk_group(t, " GPU, Dopasowanie i Rekonstrukcja (nowości ODX) ",
                                   6, 2, 824, 196)

        self.chk_gpu = self.mk_check(
            self.g_gpu, 10, 24,
            "Użyj GPU NVIDIA (obraz webodm/odx:gpu + --gpus all)", False)
        if not self._nvidia:
            self.chk_gpu.configure(state="disabled")
        self.lbl_gpu = self.mk_label(
            self.g_gpu, 10, 50,
            "Wykryto GPU NVIDIA." if self._nvidia else
            "Nie wykryto NVIDIA (karta Intel/inna) — dostępny tylko tryb CPU.",
            color=C_GREEN if self._nvidia else C_GRAY1, size=8)

        self.chk_nogpu = self.mk_check(
            self.g_gpu, 10, 74,
            "Wyłącz akcelerację GPU w ODX (--no-gpu)", not self._nvidia)

        self.mk_label(self.g_gpu, 10, 106,
                      "Dopasowywanie zdjęć (--matcher-type):")
        self.cmb_matcher = ttk.Combobox(self.g_gpu, values=MATCHERS, state="readonly",
                                        font=(UI_FAMILY, UI_SIZE))
        self.cmb_matcher.set("auto")
        self.cmb_matcher.place(x=300, y=102, width=130, height=26)

        self.mk_label(self.g_gpu, 10, 134,
                      "Algorytm SfM (--sfm-algorithm):")
        self.cmb_sfm = ttk.Combobox(self.g_gpu, values=SFM_ALGOS, state="readonly",
                                    font=(UI_FAMILY, UI_SIZE))
        self.cmb_sfm.set("incremental")
        self.cmb_sfm.place(x=300, y=130, width=130, height=26)
        self.mk_label(self.g_gpu, 450, 134,
                      "triangulation = szybciej, gdy zdjęcia mają GPS i kąty",
                      color=C_GRAY2, size=8)

        # ---- eksport ----
        self.g_exp = self.mk_group(t, " Dodatkowe Produkty Wyjściowe ", 6, 202, 824, 244)

        self.chk_pcclassify = self.mk_check(
            self.g_exp, 10, 26,
            "Klasyfikacja chmury punktów (--pc-classify)", False)
        self.chk_pccopc = self.mk_check(
            self.g_exp, 410, 26,
            "Chmura COPC dla QGIS/PDAL (--pc-copc)", False)
        self.chk_gltf = self.mk_check(
            self.g_exp, 10, 56,
            "Model GLB / glTF (--gltf)", False)
        self.chk_3dtiles = self.mk_check(
            self.g_exp, 410, 56,
            "Kafelki OGC 3D Tiles (--3d-tiles)", False)
        self.chk_kmz = self.mk_check(
            self.g_exp, 10, 86,
            "Ortofoto w Google Earth (--orthophoto-kmz)", False)
        self.chk_report = self.mk_check(
            self.g_exp, 410, 86,
            "Raport PDF (wyłączenie = --skip-report)", True)

        self.mk_label(self.g_exp, 10, 120,
                      "Rozdzielczość NMPT/NPMT (--dem-resolution cm/px):")
        self.edt_demres = ttk.Entry(self.g_exp, font=(UI_FAMILY, UI_SIZE))
        self.edt_demres.insert(0, "5")
        self.edt_demres.place(x=400, y=116, width=80, height=26)

        self.mk_label(
            self.g_exp, 10, 152,
            "GLB i 3D Tiles wymagają modelu 3D (nie działają z --skip-3dmodel ani "
            "--fast-orthophoto).",
            color=C_GRAY2, size=8)
        self.mk_label(
            self.g_exp, 10, 172,
            "COPC i klasyfikacja wymagają gęstej chmury (niedostępne przy "
            "--fast-orthophoto).",
            color=C_GRAY2, size=8)
        self.mk_label(
            self.g_exp, 10, 195,
            "Uwaga: --dtm automatycznie włącza klasyfikację chmury w ODX.",
            color=C_BLUE, size=8)

        # ---- pomoc / informacje ----
        self.g_extra = self.mk_group(t, " Pomoc i Informacje ", 6, 448, 824, 184)
        self.btn_help = ttk.Button(
            self.g_extra, text="Wszystkie opcje ODX (--help)",
            command=self.show_odx_help)
        self.btn_help.place(x=10, y=22, width=250, height=32)
        self.btn_more = ttk.Button(
            self.g_extra, text="Przejdź do zakładki: Więcej opcji ODX",
            command=lambda: self.nb.select(self.tab_more))
        self.btn_more.place(x=270, y=22, width=300, height=32)
        self.btn_redetect = ttk.Button(
            self.g_extra, text="Wykryj ODX ponownie",
            command=self.redetect_odx)
        self.btn_redetect.place(x=580, y=22, width=232, height=32)
        self.mk_label(
            self.g_extra, 10, 66,
            "Wszystkie pozostałe opcje ODX wybiera się z listy w zakładce "
            "„Więcej opcji ODX” —",
            color=C_GRAY2, size=8)
        self.mk_label(
            self.g_extra, 10, 84,
            "nic z klawiatury (m.in. --orthophoto-png, --tiles, --pc-las, "
            "--sky-removal, --end-with).",
            color=C_GRAY2, size=8)
        self.mk_label(
            self.g_extra, 10, 102,
            "Opcje przestarzałe w ODX (--verbose, --time, --resize-to, "
            "--pc-geometric...) są celowo pominięte.",
            color=C_GRAY2, size=8)
        self.lbl_engine = self.mk_label(
            self.g_extra, 10, 122, self.engine_text(),
            color=C_GREEN, size=8)

    def build_more_tab(self) -> None:
        """Zakładka 3: pozostałe opcje ODX jako checkboxy/listy (bez wpisywania)."""
        # Opcji jest wiecej niz miejsca, wiec zakladka jest przewijana.
        cv = tk.Canvas(self.tab_more, bg="#f0f0f0", highlightthickness=0,
                       yscrollincrement=28)
        vs = ttk.Scrollbar(self.tab_more, orient="vertical",
                           command=cv.yview)
        cv.configure(yscrollcommand=vs.set)
        cv.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        t = tk.Frame(cv, bg="#f0f0f0")
        cv.create_window((0, 0), window=t, anchor="nw", width=806,
                         height=MORE_TAB_HEIGHT)
        t.bind("<Configure>",
               lambda e: cv.configure(scrollregion=cv.bbox("all")))
        self._more_canvas = cv
        self._chk_more: dict[str, tk.Checkbutton] = {}
        self._ent_more: dict[str, ttk.Entry] = {}
        self._cmb_more: dict[str, ttk.Combobox] = {}

        def chk(parent, key, x, y, text, checked=False):
            c = self.mk_check(parent, x, y, text, checked)
            self._chk_more[key] = c
            return c

        def entry(parent, key, x, y, default, w=70):
            e = ttk.Entry(parent, font=(UI_FAMILY, UI_SIZE))
            e.insert(0, default)
            e.place(x=x, y=y, width=w, height=26)
            self._ent_more[key] = e
            return e

        def combo(parent, key, x, y, values, default, w=140):
            c = ttk.Combobox(parent, values=values, state="readonly",
                             font=(UI_FAMILY, UI_SIZE))
            c.set(default)
            c.place(x=x, y=y, width=w, height=26)
            self._cmb_more[key] = c
            return c

        # ---- ortofoto i kafelki ----
        g1 = self.mk_group(t, " Ortofoto i Kafelki ", 6, 2, 800, 136)
        self.chk_png = chk(g1, "opt_png", 10, 20, "Podgląd PNG (--orthophoto-png)")
        self.chk_tiles = chk(g1, "opt_tiles", 300, 20, "Kafelki (--tiles)")
        self.chk_cutline = chk(g1, "opt_cutline", 480, 20, "Cutline")
        self.chk_notiled = chk(g1, "opt_no_tiled", 10, 48,
                               "GeoTIFF pasowy (--orthophoto-no-tiled)")
        self.chk_skiportho = chk(g1, "skip_ortho", 400, 48,
                                 "Pomiń ortofoto (--skip-orthophoto)")
        self.mk_label(g1, 10, 82, "Kompresja:")
        combo(g1, "ortho_compression", 100, 78, ORTHO_COMPRESSION, "DEFLATE", 110)
        self.mk_label(g1, 230, 82, "Crop (m):")
        entry(g1, "crop", 300, 78, "3", 55)
        self.mk_label(g1, 372, 82, "0 = bez przycinania, cutline wymusza 0,01",
                      color=C_GRAY2, size=8)

        # ---- chmura punktów, model 3D, NMPT ----
        g2 = self.mk_group(t, " Chmura Punktów, Model 3D i NMPT ", 6, 140, 800, 172)
        self.chk_las = chk(g2, "pc_las", 10, 20, "LAS (--pc-las)")
        self.chk_csv = chk(g2, "pc_csv", 200, 20, "CSV (--pc-csv)")
        self.chk_ept = chk(g2, "pc_ept", 370, 20, "EPT (--pc-ept)")
        self.chk_demeuclid = chk(g2, "dem_euclidean", 530, 20,
                                 "Mapa odległości DEM")
        self.mk_label(g2, 10, 54, "pc-filter:")
        entry(g2, "pc_filter", 88, 50, "5", 55)
        self.mk_label(g2, 168, 54, "pc-sample:")
        entry(g2, "pc_sample", 255, 50, "0", 55)
        self.mk_label(g2, 335, 54, "dem-decimation:")
        entry(g2, "dem_decimation", 455, 50, "1", 55)
        self.mk_label(g2, 10, 86, "mesh-size:")
        entry(g2, "mesh_size", 95, 82, "200000", 85)
        self.mk_label(g2, 205, 86, "mesh-octree-depth 8-12:")
        entry(g2, "mesh_octree", 390, 82, "11", 55)
        self.mk_label(g2, 10, 120,
                      "0 = filtr/próbkowanie wyłączone. mesh-size i octree działają "
                      "tylko z modelem 3D.",
                      color=C_GRAY2, size=8)

        # ---- zdjęcia, GPS, kamera ----
        g3 = self.mk_group(t, " Zdjęcia, GPS i Kamera ", 6, 314, 800, 174)
        self.mk_label(g3, 10, 24, "min-num-features:")
        entry(g3, "min_features", 152, 20, "10000", 80)
        self.mk_label(g3, 258, 24, "feature-type:")
        combo(g3, "feature_type", 362, 20, FEATURE_TYPES, "dspsift", 110)
        self.mk_label(g3, 10, 56, "gps-accuracy (m):")
        entry(g3, "gps_accuracy", 152, 52, "3", 70)
        self.mk_label(g3, 258, 56, "camera-lens:")
        combo(g3, "camera_lens", 362, 52, CAMERA_LENSES, "auto", 150)
        self.chk_forcegps = chk(g3, "force_gps", 10, 86,
                                "EXIF GPS ważniejszy od GCP (--force-gps)")
        self.chk_ignoregsd = chk(g3, "ignore_gsd", 420, 86,
                                 "Ignoruj GSD (--ignore-gsd)")
        self.chk_fixedcam = chk(g3, "fixed_camera", 10, 114,
                                "Stałe parametry kamery")
        self.chk_rolling = chk(g3, "rolling_shutter", 420, 114, "Rolling shutter")

        # ---- maski AI, wideo, raport ----
        g4 = self.mk_group(t, " Maski AI, Wideo i Raport ", 6, 490, 800, 140)
        self.chk_sky = chk(g4, "sky_removal", 10, 20,
                           "Usuwanie nieba AI (--sky-removal)")
        self.chk_bg = chk(g4, "bg_removal", 400, 20,
                          "Usuwanie tła (--bg-removal)")
        self.mk_label(g4, 10, 54, "video-limit:")
        entry(g4, "video_limit", 100, 50, "500", 65)
        self.mk_label(g4, 180, 54, "video-resolution:")
        entry(g4, "video_res", 305, 50, "4000", 70)
        self.mk_label(g4, 390, 54, "report-units:")
        combo(g4, "report_units", 490, 50, REPORT_UNITS, "m", 120)
        self.mk_label(g4, 10, 86, "Zakończ na etapie (--end-with):")
        combo(g4, "end_with", 228, 82, END_STAGES, "odm_postprocess", 180)
        self.mk_label(g4, 420, 86, "np. odm_orthophoto = bez raportu i postprocessingu",
                      color=C_GRAY2, size=8)

        # ---- georeferencja, fotopunkty, SfM ----
        g5 = self.mk_group(t, " Georeferencja, GCP i SfM ", 6, 634, 800, 212)
        chk(g5, "use_exif", 10, 18, "Tylko GPS z EXIF (--use-exif)")
        chk(g5, "hybrid_ba", 410, 18, "Hybrydowa wiązka BA (szybciej)")
        chk(g5, "sfm_no_partial", 10, 46, "Bez częściowych modeli SfM")
        chk(g5, "sm_no_align", 410, 46, "Submodele bez wyrównania")
        self.mk_label(g5, 10, 80, "matcher-neighbors:")
        entry(g5, "matcher_neighbors", 150, 76, "0", 70)
        self.mk_label(g5, 240, 80, "gps-z-offset (m):")
        entry(g5, "gps_z_offset", 370, 76, "0", 60)
        self.mk_label(g5, 10, 112, "Granica GeoJSON (--boundary):")
        entry(g5, "boundary", 190, 108, "", 460)
        self.mk_label(g5, 10, 144, "Plik geo (--geo) / align (--align):")
        entry(g5, "geo", 230, 140, "", 250)
        entry(g5, "align", 500, 140, "", 150)

        # ---- splity, DEM, tekstury ----
        g6 = self.mk_group(t, " Splity, DEM i Tekstury ", 6, 854, 800, 184)
        self.mk_label(g6, 10, 24, "split:")
        entry(g6, "split", 60, 20, "999999", 70)
        self.mk_label(g6, 150, 24, "split-overlap (m):")
        entry(g6, "split_overlap", 280, 20, "150", 60)
        self.mk_label(g6, 360, 24, "smrf-window (m):")
        entry(g6, "smrf_window", 480, 20, "18", 60)
        self.mk_label(g6, 10, 56, "dem-gapfill-steps:")
        entry(g6, "dem_gapfill", 150, 52, "3", 60)
        chk(g6, "pc_skip_geom", 240, 52, "Bez atrybutów geometrycznych chmury")
        chk(g6, "tex_skip_seam", 10, 84, "Bez wyrównywania szwów tekstury")
        chk(g6, "tex_keep_unseen", 410, 84, "Zachowaj niewidoczne ściany")
        chk(g6, "tex_single_mat", 10, 112, "Jedna tekstura dla modelu")
        self.mk_label(g6, 330, 116, "Kopiuj wyniki (--copy-to):")
        entry(g6, "copy_to", 520, 112, "", 150)

        # ---- multispektralne ----
        g7 = self.mk_group(t, " Multispektralne ", 6, 1046, 800, 124)
        self.mk_label(g7, 10, 24, "Kalibracja radiometryczna:")
        combo(g7, "radiometric", 200, 20, RADIOMETRIC, "none", 150)
        self.mk_label(g7, 370, 24, "primary-band:")
        entry(g7, "primary_band", 470, 20, "", 170)
        chk(g7, "skip_band_align", 10, 56, "Bez wyrównania pasm (multispektralne)")

        # ---- wlasne flagi ----
        g8 = self.mk_group(t, " Własne Flagi (nietypowe / nowe opcje) ",
                           6, 1178, 800, 118)
        self.mk_label(
            g8, 10, 20,
            "Parametry spoza listy – wpisz ręcznie, cudzysłów dla spacji:")
        self.edt_extra = tk.Text(g8, font=(MONO_FAMILY, UI_SIZE), wrap="char",
                                 height=2, bg="white", relief="solid", bd=1)
        self.edt_extra.place(x=10, y=42, width=770, height=44)
        self.mk_label(
            g8, 10, 92,
            'Przykład: --min-num-features 20000  --boundary "C:\a.geojson"',
            color=C_GRAY2, size=8)

    def manual_text(self) -> str:
        """Tresc pola wlasnych flag (moze nie istniec w starych oknach)."""
        try:
            return self.edt_extra.get("1.0", "end").strip()
        except (AttributeError, tk.TclError):
            return ""

    def manual_argv(self) -> list[str]:
        """Wlasne flagi jako lista argumentow (blad cudzyslowu -> pusto)."""
        try:
            return split_extra_args(self.manual_text())
        except ValueError:
            return []

    def _sync_scrollbar(self, event=None) -> None:
        """Pokazuje pasek tylko wtedy, gdy formularz nie mieści się w oknie."""
        try:
            self.rootframe.update_idletasks()
            need = 968 > self.canvas.winfo_height() + 2
            mapped = bool(self.vbar.winfo_ismapped())
            if need and not mapped:
                self.vbar.pack(side="right", fill="y")
            elif not need and mapped:
                self.vbar.pack_forget()
        except tk.TclError:
            pass

    def _on_mousewheel(self, event) -> None:
        if self.canvas.winfo_height() >= 968:
            return
        num = getattr(event, "num", None)
        if num == 4:
            step = -1
        elif num == 5:
            step = 1
        else:
            delta = getattr(event, "delta", 0)
            step = -1 if delta > 0 else 1
            if abs(delta) >= 120:
                step = int(-delta / 120)
        self.canvas.yview_scroll(step, "units")

    def assign_events(self) -> None:
        for w in (self.edt_folder, self.edt_ortho, self.edt_threads,
                  self.edt_demres):
            w.bind("<KeyRelease>", lambda e: self.on_any_change())
        for w in (self.cmb_feat, self.cmb_pc, self.cmb_matcher, self.cmb_sfm):
            w.bind("<<ComboboxSelected>>", lambda e: self.on_any_change())
        for w in self._ent_more.values():
            w.bind("<KeyRelease>", lambda e: self.on_any_change())
        for w in self._cmb_more.values():
            w.bind("<<ComboboxSelected>>", lambda e: self.on_any_change())
        for w in self._chk_more.values():
            w.configure(command=self.on_any_change)
        for w in (self.chk_dsm, self.chk_dtm, self.chk_rerun, self.chk_optdisk,
                  self.chk_skip3d, self.chk_cog, self.chk_autobound,
                  self.chk_fastortho, self.chk_use3dmesh, self.chk_gpu,
                  self.chk_nogpu, self.chk_pcclassify, self.chk_pccopc,
                  self.chk_gltf, self.chk_3dtiles, self.chk_kmz, self.chk_report):
            w.configure(command=self.on_any_change)

    def on_any_change(self) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.update_exclusions()
            self.update_all()
        finally:
            self._updating = False

    # ---------------- konfiguracja (JSON) ----------------
    def load_config(self) -> dict:
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def cfg_str(self, key: str, default: str) -> str:
        v = self.cfg.get(key, default)
        return v if isinstance(v, str) else default

    def cfg_bool(self, key: str, default: bool) -> bool:
        v = self.cfg.get(key, default)
        return v if isinstance(v, bool) else default

    def restore_settings(self) -> None:
        if not self.cfg:
            return
        folder = self.cfg_str("last_folder", "")
        if folder:
            self.edt_folder.delete(0, "end")
            self.edt_folder.insert(0, folder)

        for entry, key in ((self.edt_ortho, "ortho_res"),
                           (self.edt_threads, "threads"),
                           (self.edt_demres, "dem_res")):
            val = self.cfg_str(key, entry.get())
            entry.delete(0, "end")
            entry.insert(0, val)

        self.cmb_feat.set(self.cfg_str("feat_qual", self.cmb_feat.get()))
        self.cmb_pc.set(self.cfg_str("pc_qual", self.cmb_pc.get()))
        self.cmb_matcher.set(self.cfg_str("matcher", self.cmb_matcher.get()))
        self.cmb_sfm.set(self.cfg_str("sfm", self.cmb_sfm.get()))

        for chk, key in ((self.chk_dsm, "dsm"), (self.chk_dtm, "dtm"),
                         (self.chk_rerun, "rerun"), (self.chk_skip3d, "skip_3d"),
                         (self.chk_cog, "cog"), (self.chk_autobound, "auto_bound"),
                         (self.chk_fastortho, "fast_ortho"),
                         (self.chk_use3dmesh, "use_3dmesh"),
                         (self.chk_optdisk, "opt_disk"), (self.chk_gpu, "use_gpu"),
                         (self.chk_nogpu, "no_gpu"),
                         (self.chk_pcclassify, "pc_classify"),
                         (self.chk_pccopc, "pc_copc"), (self.chk_gltf, "gltf"),
                         (self.chk_3dtiles, "three_d_tiles"), (self.chk_kmz, "kmz"),
                         (self.chk_report, "report")):
            chk.var.set(self.cfg_bool(key, chk.var.get()))

        for key, entry in self._ent_more.items():
            val = self.cfg_str(key, entry.get())
            entry.delete(0, "end")
            entry.insert(0, val)
        for key, cmb in self._cmb_more.items():
            cmb.set(self.cfg_str(key, cmb.get()))
        for key, chk in self._chk_more.items():
            chk.var.set(self.cfg_bool(key, chk.var.get()))
        extra = self.cfg_str("extra", "")
        if extra:
            self.edt_extra.delete("1.0", "end")
            self.edt_extra.insert("1.0", extra)

    def save_config(self) -> None:
        data = {
            "last_folder": self.edt_folder.get(),
            "ortho_res": self.edt_ortho.get(),
            "threads": self.edt_threads.get(),
            "dem_res": self.edt_demres.get(),
            "feat_qual": self.cmb_feat.get(),
            "pc_qual": self.cmb_pc.get(),
            "matcher": self.cmb_matcher.get(),
            "sfm": self.cmb_sfm.get(),
            "dsm": self.chk_dsm.var.get(),
            "dtm": self.chk_dtm.var.get(),
            "rerun": self.chk_rerun.var.get(),
            "skip_3d": self.chk_skip3d.var.get(),
            "cog": self.chk_cog.var.get(),
            "auto_bound": self.chk_autobound.var.get(),
            "fast_ortho": self.chk_fastortho.var.get(),
            "use_3dmesh": self.chk_use3dmesh.var.get(),
            "opt_disk": self.chk_optdisk.var.get(),
            "use_gpu": self.chk_gpu.var.get(),
            "no_gpu": self.chk_nogpu.var.get(),
            "pc_classify": self.chk_pcclassify.var.get(),
            "pc_copc": self.chk_pccopc.var.get(),
            "gltf": self.chk_gltf.var.get(),
            "three_d_tiles": self.chk_3dtiles.var.get(),
            "kmz": self.chk_kmz.var.get(),
            "report": self.chk_report.var.get(),
            "odx_dir": self._odx_dir,
            "extra": self.manual_text(),
        }
        for key, chk in self._chk_more.items():
            data[key] = chk.var.get()
        for key, entry in self._ent_more.items():
            data[key] = entry.get()
        for key, cmb in self._cmb_more.items():
            data[key] = cmb.get()
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ---------------- logika (UpdateExclusions / EstimateTime) ----------------
    def update_exclusions(self) -> None:
        """Wykluczenia jak w config.py ODX + ochrona nowych opcji."""
        fast = self.chk_fastortho.var.get()
        use3d = self.chk_use3dmesh.var.get()
        skip3d = self.chk_skip3d.var.get()

        # --fast-orthophoto / --skip-3dmodel vs --use-3dmesh
        if fast:
            # zapamiętaj stan --skip-3dmodel, żeby po wyłączeniu fast go przywrócić
            if self._fast_block_prev is None:
                self._fast_block_prev = self.chk_skip3d.var.get()
            self.chk_use3dmesh.var.set(False)
            self.chk_use3dmesh.configure(state="disabled")
            self.chk_skip3d.var.set(True)
            self.chk_skip3d.configure(state="disabled")
        elif use3d:
            self.chk_fastortho.var.set(False)
            self.chk_fastortho.configure(state="disabled")
            self.chk_skip3d.var.set(False)
            self.chk_skip3d.configure(state="disabled")
        else:
            self.chk_use3dmesh.configure(state="normal")
            self.chk_fastortho.configure(state="normal")
            self.chk_skip3d.configure(state="normal")
            if self._fast_block_prev is not None:
                self.chk_skip3d.var.set(self._fast_block_prev)
                self._fast_block_prev = None

        fast = self.chk_fastortho.var.get()
        skip3d = self.chk_skip3d.var.get()
        dense_ok = not fast
        model_ok = not (skip3d or fast)

        # gęsta chmura: NMPT/NPMT, klasyfikacja, COPC
        for chk in (self.chk_dsm, self.chk_dtm,
                    self.chk_pcclassify, self.chk_pccopc):
            chk.configure(state="normal" if dense_ok else "disabled")

        # model 3D: GLB, 3D Tiles
        for chk in (self.chk_gltf, self.chk_3dtiles):
            chk.configure(state="normal" if model_ok else "disabled")

        # rozdzielczość DEM ma sens tylko z NMPT/NPMT
        dem_on = self.chk_dsm.var.get() or self.chk_dtm.var.get()
        self.edt_demres.configure(state="normal" if dem_on else "disabled")

        # GPU
        self.chk_gpu.configure(state="normal" if self._nvidia else "disabled")
        if not self._nvidia:
            self.chk_gpu.var.set(False)
        use_gpu = self.chk_gpu.var.get()
        self.chk_nogpu.configure(state="disabled" if use_gpu else "normal")
        if use_gpu:
            self.chk_nogpu.var.set(False)

        # hamming wymaga GPU
        if self.cmb_matcher.get() == "hamming" and not self._gpu_active():
            self.cmb_matcher.set("auto")

        # ---- zakładka "Więcej opcji ODX" ----
        ortho_on = not self._chk_more["skip_ortho"].var.get()
        for key in ("opt_png", "opt_tiles", "opt_cutline", "opt_no_tiled"):
            self._chk_more[key].configure(
                state="normal" if ortho_on else "disabled")
        self._cmb_more["ortho_compression"].configure(
            state="readonly" if ortho_on else "disabled")

        # --orthophoto-cutline wymusza w ODX crop = 0.01 m
        cutline = (ortho_on and self._chk_more["opt_cutline"].var.get())
        self._ent_more["crop"].configure(
            state="normal" if (ortho_on and not cutline) else "disabled")

        dense_keys = ("pc_las", "pc_csv", "pc_ept")
        for key in dense_keys:
            self._chk_more[key].configure(
                state="normal" if dense_ok else "disabled")
        for key in ("pc_filter", "pc_sample"):
            self._ent_more[key].configure(
                state="normal" if dense_ok else "disabled")

        dem_on = self.chk_dsm.var.get() or self.chk_dtm.var.get()
        self._ent_more["dem_decimation"].configure(
            state="normal" if dem_on else "disabled")
        self._chk_more["dem_euclidean"].configure(
            state="normal" if dem_on else "disabled")

        for key in ("mesh_size", "mesh_octree"):
            self._ent_more[key].configure(
                state="normal" if model_ok else "disabled")

    def update_hint(self) -> None:
        """Podpowiedź pod flagami: ostrzega o 1 cm/px w trybie ekspresowym."""
        try:
            res = float(self.edt_ortho.get().replace(",", "."))
        except ValueError:
            res = 0.0
        if self.chk_fastortho.var.get() and 0 < res < 2.0:
            self.lbl_hint.configure(
                text=f"Tryb ekspresowy z {res:g} cm/px: --fast-orthophoto liczy ortofoto "
                     f"z rzadkiej chmury — ustaw 2–5 cm/px.",
                fg=C_DARKRED)
        else:
            self.lbl_hint.configure(
                text="Wskazówka: przy 7,6 GB RAM pozostaw --max-concurrency 4 "
                     "i jakość medium.",
                fg=C_BLUE)

    def _gpu_active(self) -> bool:
        return self._nvidia and self.chk_gpu.var.get() and not self.chk_nogpu.var.get()

    def estimate_time(self, img_count: int, video_count: int = 0) -> str:
        if img_count == 0 and video_count == 0:
            return "Brak zdjęć do analizy"
        if img_count == 0:
            return (f"{video_count} wideo — czas po ekstrakcji klatek "
                    f"(limit 500)")

        qual = self.cmb_feat.get()
        sec = SEC_PER_IMG.get(qual, 22)
        if self.chk_skip3d.var.get():
            sec *= 0.6
        if self.chk_fastortho.var.get():
            sec *= 0.3
        if self._gpu_active():
            sec *= 0.8

        minutes = int(img_count * sec) // 60
        hours, rem = divmod(minutes, 60)
        suffix = f" + {video_count} wideo" if video_count else ""
        if hours > 0:
            return (f"ok. {hours} godz. {rem} min "
                    f"(dla {img_count} zdjęć{suffix} w jakości '{qual}')")
        return f"ok. {minutes} min (dla {img_count} zdjęć{suffix} w jakości '{qual}')"

    def apply_express_preset(self) -> None:
        """Preset szybki: ortofoto z rzadkiej chmury ~3 cm/px, bez modelu i raportu."""
        self._updating = True
        self._fast_block_prev = None
        try:
            self.chk_use3dmesh.var.set(False)
            self.chk_fastortho.var.set(True)      # wyłącza gęstą chmurę i model 3D
            self.chk_skip3d.var.set(True)
            self.chk_dsm.var.set(False)           # DEM wymaga gęstej chmury
            self.chk_dtm.var.set(False)
            self.chk_cog.var.set(True)
            self.chk_autobound.var.set(True)
            self.chk_optdisk.var.set(False)
            # bez --rerun-all: preset ma byc szybki, a nie kasowac wyniki
            self.chk_rerun.var.set(False)
            self._cmb_more["end_with"].set("odm_postprocess")
            self.chk_report.var.set(False)        # --skip-report
            self.cmb_feat.set("medium")
            self.cmb_pc.set("low")                # przy fast-ortho i tak nieużywane
            self.cmb_matcher.set("auto")
            self.cmb_sfm.set("incremental")
            # tryb ekspresowy ma dać ortofoto: bez --skip-orthophoto,
            # bez maski AI i bez eksportów chmury (spowalniają)
            self._chk_more["skip_ortho"].var.set(False)
            for key in ("sky_removal", "bg_removal", "pc_las", "pc_csv", "pc_ept",
                        "opt_png", "opt_tiles", "opt_cutline", "opt_no_tiled"):
                self._chk_more[key].var.set(False)
            for entry, value in ((self.edt_ortho, "2.0"), (self.edt_threads, "4"),
                                 (self.edt_demres, "5")):
                entry.delete(0, "end")
                entry.insert(0, value)
            self.update_exclusions()
            self.update_all()
        finally:
            self._updating = False

    def apply_night_preset(self) -> None:
        """Preset pod wielogodzinny przebieg: maksymalna jakość, stabilna pamięć."""
        self._updating = True
        self._fast_block_prev = None
        try:
            self.chk_fastortho.var.set(False)
            self.chk_use3dmesh.var.set(False)
            self.chk_skip3d.var.set(False)
            self.chk_dsm.var.set(True)
            self.chk_dtm.var.set(True)
            self.chk_cog.var.set(True)
            self.chk_autobound.var.set(True)
            self.chk_report.var.set(True)
            # --rerun-all kasuje poprzednie wyniki: przy nocnym przebiegu
            # lepiej móc wznowić po ewentualnej awarii (np. braku RAM).
            self.chk_rerun.var.set(False)
            self.chk_optdisk.var.set(False)
            self._cmb_more["end_with"].set("odm_postprocess")
            self._chk_more["skip_ortho"].var.set(False)
            self.cmb_feat.set("high")
            self.cmb_pc.set("high")
            self.cmb_matcher.set("auto")
            self.cmb_sfm.set("incremental")
            for entry, value in ((self.edt_ortho, "1.0"), (self.edt_threads, "2"),
                                 (self.edt_demres, "2.5")):
                entry.delete(0, "end")
                entry.insert(0, value)
            self.update_exclusions()
            self.update_all()
        finally:
            self._updating = False

    def current_opts(self) -> dict:
        def as_int(text: str, default: int) -> int:
            try:
                v = int(str(text).strip())
                return v if v > 0 else default
            except ValueError:
                return default

        def as_float_text(text: str, default: str) -> str:
            try:
                v = float(str(text).replace(",", ".").strip())
                return str(v) if v > 0 else default
            except ValueError:
                return default

        opts = {
            "ortho_res": as_float_text(self.edt_ortho.get(), "2.0"),
            "threads": as_int(self.edt_threads.get(), 4),
            "feat_qual": self.cmb_feat.get() or "medium",
            "pc_qual": self.cmb_pc.get() or "medium",
            "dsm": self.chk_dsm.var.get(),
            "dtm": self.chk_dtm.var.get(),
            "rerun": self.chk_rerun.var.get(),
            "skip_3d": self.chk_skip3d.var.get(),
            "cog": self.chk_cog.var.get(),
            "auto_bound": self.chk_autobound.var.get(),
            "fast_ortho": self.chk_fastortho.var.get(),
            "use_3dmesh": self.chk_use3dmesh.var.get(),
            "opt_disk": self.chk_optdisk.var.get(),
            "use_gpu": self._gpu_active(),
            "no_gpu": self.chk_nogpu.var.get(),
            "matcher": self.cmb_matcher.get() or "auto",
            "sfm": self.cmb_sfm.get() or "incremental",
            "dem_res": as_float_text(self.edt_demres.get(), "5"),
            "pc_classify": self.chk_pcclassify.var.get(),
            "pc_copc": self.chk_pccopc.var.get(),
            "gltf": self.chk_gltf.var.get(),
            "three_d_tiles": self.chk_3dtiles.var.get(),
            "kmz": self.chk_kmz.var.get(),
            "report": self.chk_report.var.get(),
            "extra_args": self.manual_argv(),
            "odx_dir": self._odx_dir,
        }
        for key, chk in self._chk_more.items():
            opts[key] = chk.var.get()
        for key, entry in self._ent_more.items():
            opts[key] = entry.get().strip()
        for key, cmb in self._cmb_more.items():
            opts[key] = cmb.get()
        return opts

    def command_argv_and_gcp(self, folder: str) -> tuple[list[str], str, int, str]:
        gcp_path, gcp_count, srs = detect_gcp(folder)
        gcp_arg = ""
        if gcp_path:
            gcp_arg = gcp_path if IS_WINDOWS else (
                "/datasets/" + os.path.basename(folder) + "/" + os.path.basename(gcp_path))
        argv = build_command(folder, gcp_arg, self.current_opts())
        if not self._docker_ok and not IS_WINDOWS:
            argv = ["sg", "docker", "-c", shlex.join(argv)]
        return argv, gcp_path, gcp_count, srs

    def conflict_notes(self) -> list[str]:
        """Flagi, ktore w danym trybie nic nie robia, i bledy wlasnych flag."""
        notes = []
        try:
            split_extra_args(self.manual_text())
        except ValueError:
            notes.append("BŁĄD: niedomknięty cudzysłów we własnych flagach ODX")
        if not self.chk_fastortho.var.get():
            return notes
        martwe = []
        for key, flag in (("pc_las", "--pc-las"), ("pc_csv", "--pc-csv"),
                          ("pc_ept", "--pc-ept"), ("dem_euclidean",
                                                   "--dem-euclidean-map")):
            if self._chk_more[key].var.get():
                martwe.append(flag)
        for key, flag in (("mesh_size", "--mesh-size"),
                          ("mesh_octree", "--mesh-octree-depth")):
            val = self._ent_more[key].get().strip()
            if val and val != MORE_VALUE_DEFAULTS[key]:
                martwe.append(flag)
        if martwe:
            notes.append("Tryb ekspresowy nie tworzy chmury gęstej ani modelu "
                         "– ignorowane: " + ", ".join(martwe))
        if self._chk_more["skip_ortho"].var.get():
            notes.append("--skip-orthophoto wyłącza jedyny produkt trybu "
                         "ekspresowego (ortofotomapę)")
        if self.manual_text():
            notes.append("własne flagi są dopisywane na końcu – przy "
                         "powtórzonej fladze ODX użyje ostatniej wartości")
        return notes

    def update_all(self) -> None:
        self.update_exclusions()
        self.update_hint()
        folder = project_folder(normalize_path(self.edt_folder.get()))

        count, videos, in_sub = scan_assets(folder)
        if count > 0:
            if in_sub:
                self.lbl_photo.configure(
                    text=f" Status zdjęć: Wykryto {count} plików w podfolderze /images",
                    fg=C_GREEN)
            else:
                self.lbl_photo.configure(
                    text=f" Status zdjęć: Wykryto {count} plików luzem "
                         f"(zostaną przeniesione do /images)",
                    fg=C_BLUE2)
        else:
            self.lbl_photo.configure(
                text=" Status zdjęć: Brak plików obrazu (JPG/PNG/TIF/DNG...)",
                fg=C_DARKRED)

        if videos:
            self.lbl_video.configure(
                text=f" Status wideo: {videos} plik(ów) — ODX wyodrębni klatki"
                     f"{' (GPS z .srt)' if collect_sidecars(os.path.join(folder, 'images') if in_sub else folder) else ''}",
                fg=C_GREEN)
        else:
            self.lbl_video.configure(text=" Status wideo: brak filmów", fg=C_GRAY1)

        preview_note = ""
        if folder and os.path.isdir(folder):
            argv, gcp_path, gcp_count, srs = self.command_argv_and_gcp(folder)
        else:
            # Brak folderu: podgląd ma mimo wszystko reagować na zmiany opcji.
            name = os.path.basename(folder) if folder else "nazwa-projektu"
            fallback = os.path.join(
                str(Path.home() / "ODX" / "projects"), name)
            argv = build_command(fallback, "", self.current_opts())
            if not IS_WINDOWS and not self._docker_ok:
                argv = ["sg", "docker", "-c", shlex.join(argv)]
            gcp_path, gcp_count, srs = "", 0, ""
            preview_note = ("# Podgląd przykładowy - wskaż folder projektu, "
                            "aby zobaczyć docelowe ścieżki.\n")

        if gcp_path:
            self.lbl_gcp.configure(
                text=f" Status GCP: Znaleziono '{os.path.basename(gcp_path)}' | "
                     f"Wierszy fotopunktów: {gcp_count} | Układ: {srs}",
                fg=C_GREEN)
        else:
            self.lbl_gcp.configure(
                text=" Status GCP: Brak pliku fotopunktów "
                     "(wykorzystane zostaną tylko dane EXIF GPS)",
                fg=C_GRAY2)

        self.lbl_time.configure(
            text="Szacowany czas: " + self.estimate_time(count, videos))

        notes = self.conflict_notes()
        if notes:
            preview_note = preview_note + "".join(
                "# %s\n" % n for n in notes)

        preview = preview_note + format_command(argv)
        if not self._docker_ok:
            if IS_WINDOWS:
                preview = ("# UWAGA: Docker nie odpowiada - uruchom Docker Desktop "
                           "i spróbuj ponownie.\n" + preview)
            else:
                preview = ("# UWAGA: brak dostępu do demona Docker w tej sesji "
                           "(nowa grupa 'docker' działa po przelogowaniu) - użyto sg.\n"
                           + preview)
        self.memo.configure(state="normal")
        self.memo.delete("1.0", "end")
        self.memo.insert("1.0", preview)
        self.memo.configure(state="disabled")

        self.save_config()

    # ---------------- zdarzenia ----------------
    def btn_browse_click(self) -> None:
        current = normalize_path(self.edt_folder.get())
        initial = current if os.path.isdir(current) else str(Path.home())
        chosen = filedialog.askdirectory(
            title="Wskaż folder projektu ze zdjęciami", initialdir=initial)
        if chosen:
            self._updating = True
            self.edt_folder.delete(0, "end")
            self.edt_folder.insert(0, normalize_path(chosen))
            self._updating = False
            self.update_all()

    def btn_run_click(self) -> None:
        self.run_odx()

    def engine_text(self) -> str:
        """Opis silnika: natywny run.bat (Windows) albo obraz Dockera (Linux)."""
        if IS_WINDOWS:
            dirn = self._odx_dir or "-"
            return ("Silnik: ODX natywny - "
                    + os.path.join(dirn, "run.bat")
                    + "  (wykryty raz, zapisany w config.json)")
        return f"Obraz: {ODX_IMAGE}   |   wersja ODX 3.8.4"

    def redetect_odx(self) -> None:
        """Ponowne, jednorazowe skanowanie instalacji ODX (na życzenie)."""
        if not IS_WINDOWS:
            messagebox.showinfo(
                "Tryb Linux",
                "Na Linuksie ODX działa z obrazu Dockera -\n"
                f"nie ma czego wykrywać ({ODX_IMAGE}).")
            return
        self._odx_dir = redetect_odx_dir()
        self.lbl_engine.configure(text=self.engine_text())
        self.save_config()
        self.update_all()
        ok = os.path.isfile(os.path.join(self._odx_dir, "run.bat"))
        messagebox.showinfo(
            "Wykrywanie ODX",
            ("Znaleziono: " if ok else "Nie znaleziono run.bat w: ")
            + self._odx_dir
            + ("\n\nŚcieżka zapisana w config.json - kolejne starty jej nie szukają."
               if ok else
               "\n\nUstaw zmienną ODX_HOME na folder z run.bat i spróbuj ponownie."))

    def show_odx_help(self) -> None:
        if IS_WINDOWS:
            cmd = [os.path.join(self._odx_dir or detect_odx_dir(), "run.bat"),
                   "--help"]
        else:
            cmd = ["docker", "run", "--rm", ODX_IMAGE, "--help"]
        try:
            if IS_WINDOWS:
                subprocess.Popen(
                    ["cmd.exe", "/k", subprocess.list2cmdline(cmd)],
                    cwd=str(Path.home()),
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
                return
            term = pick_terminal()
            if not term:
                messagebox.showerror("Brak terminala",
                                     "Nie znaleziono emulatora terminala.")
                return
            subprocess.Popen(
                term + ["bash", "-c",
                        shlex.join(cmd) + "; echo; read -n 1 -r -p 'Naciśnij klawisz...' _"],
                cwd=str(Path.home()), start_new_session=True)
        except OSError as exc:
            messagebox.showerror("Błąd", f"Nie udało się otworzyć pomocy:\n{exc}")

    def run_odx(self) -> None:
        folder = project_folder(normalize_path(self.edt_folder.get()))
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning(
                "Brak katalogu",
                "Wskaż istniejący katalog projektu ze zdjęciami.\n\n" + folder)
            return

        count, videos, in_sub = scan_assets(folder)
        if count == 0 and videos == 0:
            messagebox.showwarning(
                "Brak zdjęć",
                "Nie znaleziono plików obrazu ani wideo we wskazanym katalogu:\n"
                + folder)
            return

        # zdjęcia/filmy "luzem" przenosimy do podkatalogu images
        if not in_sub:
            img_dir = folder if os.path.basename(folder).lower() == "images" \
                else os.path.join(folder, "images")
            try:
                os.makedirs(img_dir, exist_ok=True)
                for src in (collect_images(folder) + collect_videos(folder)
                            + collect_sidecars(folder)):
                    shutil.move(src, os.path.join(img_dir, os.path.basename(src)))
            except OSError as exc:
                messagebox.showerror("Błąd", f"Nie udało się przenieść plików:\n{exc}")
                return
            self._updating = True
            self.update_all()
            self._updating = False

        self._docker_ok = True if IS_WINDOWS else docker_available()
        argv, gcp_path, _, _ = self.command_argv_and_gcp(folder)
        project_name = os.path.basename(folder.rstrip(os.sep))

        # skrypt startowy: run_tmp.bat na Windows, run_tmp.sh na Linux
        script = (make_windows_script(argv, folder, project_name)
                  if IS_WINDOWS else make_posix_script(argv, folder, project_name))
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            RUN_SCRIPT.write_text(script, encoding="utf-8")
            if not IS_WINDOWS:
                RUN_SCRIPT.chmod(0o755)
        except OSError as exc:
            messagebox.showerror("Błąd",
                                 f"Nie udało się zapisać skryptu startowego:\n{exc}")
            return

        self.save_config()

        try:
            if IS_WINDOWS:
                subprocess.Popen(
                    ["cmd.exe", "/c", str(RUN_SCRIPT)],
                    cwd=str(Path.home()),
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            else:
                term = pick_terminal()
                if not term:
                    messagebox.showerror(
                        "Brak terminala",
                        "Nie znaleziono emulatora terminala (konsole/xterm/...).\n"
                        f"Uruchom ręcznie:\n\nbash {RUN_SCRIPT}")
                    return
                subprocess.Popen(term + ["bash", str(RUN_SCRIPT)],
                                 cwd=str(Path.home()), start_new_session=True)
        except OSError as exc:
            messagebox.showerror("Błąd uruchomienia",
                                 f"Nie udało się uruchomić procesu ODX:\n{exc}")
            return

        # okno GUI zostaje otwarte (jak w wersji ODM)

    def on_close(self) -> None:
        try:
            self.save_config()
        except Exception:
            pass
        self.destroy()


def main() -> int:
    app = ODXForm()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
