# ODX Manager - jeden interfejs (Windows natywny / Debian + Docker)

Ten sam plik GUI (`gui/odx_gui.py`) dziala na obu systemach - rozni sie tylko silnik:

| | Windows | Debian 13 / Linux |
|---|---|---|
| silnik | natywny `run.bat` (ODX for Windows) | `docker run webodm/odx` (opcjonalnie `:gpu` + `--gpus all`) |
| wykrywanie | `_python_path.bat` -> `_python_cache.txt`, `_find_odx.bat` -> `ODX_DIR` | obraz Docker (`ODX_IMAGE`, domyslnie `webodm/odx:latest`) + sciezka z configu |
| konfiguracja | `%APPDATA%\odx-gui\config.json` | `~/.config/odx-gui/config.json` |
| launcher | `Uruchom ODX Manager.bat` | `./uruchom-odx-manager.sh` |

## Instalacja

### Windows

```
git clone https://github.com/gracy72/odx-manager.git
cd odx-manager
```

Wymagania: Python 3 z Tkinterem (instalator z python.org, opcja *tcl/tk and IDLE*)
oraz ODX for Windows (katalog z `run.bat`, np. `C:\Users\<user>\Portable\ODX`).

- start: dwuklik **`Uruchom ODX Manager.bat`** (bez okna konsoli),
- diagnostyka: **`Uruchom ODX Manager - konsola.bat`** albo `test_srodowiska.bat`,
- skrot na pulpicie z ikona: `powershell -ExecutionPolicy Bypass -File create_shortcut.ps1`.

Interpreter Pythona wykrywany jest raz i zapisywany w `_python_cache.txt`
(kolejne starty nie uruchamiaja PowerShella). Wskazanie reczne:
`set ODX_GUI_PYTHON=C:\Python313\python.exe`, wymuszenie ponownego wykrycia:
usun `_python_cache.txt`.

### Debian 13 / Linux

```
git clone https://github.com/gracy72/odx-manager.git
cd odx-manager
chmod +x uruchom-odx-manager.sh
sudo apt install python3 python3-tk docker.io
sudo docker pull webodm/odx:latest      # wariant GPU: webodm/odx:gpu
./uruchom-odx-manager.sh
```

Silnikiem na Linuksie jest obraz Dockera; mozna go podmienic bez zmiany kodu:

```
ODX_IMAGE=webodm/odx:gpu ./uruchom-odx-manager.sh
```

Jesli `docker` wymaga sudo: `sudo usermod -aG docker $USER` i przelogowanie
(GUI potrafi tez uzyc `sg docker -c`).

## Zakladki

1. **Projekt i jakosc** - folder, rozdzielczosci, watki, glowne flagi, dwa presety.
2. **Opcje ODX / zaawansowane** - GPU, matcher, SfM, produkty dodatkowe.
3. **Wiecej opcji ODX** (przewijana) - wszystkie pozostale flagi ODX 3.8.4:
   ortofoto/kafelki, chmura/model/NMPT, zdjecia/GPS/kamera, maski AI/wideo/raport,
   georeferencja i GCP, splity/DEM/tekstury, multispektralne oraz
   **pole wlasnych flag** (dowolna nowa opcja bez zmiany kodu).

## Presety

| | Nocna jakosc | Ekspres |
|---|---|---|
| kolejnosc | maks. jakosc, stabilna pamiec | szybkie ortofoto ze sparse cloud |
| `--feature-quality` / `--pc-quality` | high / high | medium / low |
| `--max-concurrency` | 2 | 4 |
| orto | 1,0 cm/px | 2,0 cm/px |
| DEM | `--dsm --dtm`, 2,5 | brak (fast-ortho i tak go nie liczy) |
| inne | `--rerun-all` wylaczone (wznowienie po awarii) | `--fast-orthophoto --skip-report` |

## Diagnostyka

- `test_srodowiska.bat` - Python + Tkinter + `run.bat --version`.
- `%APPDATA%\odx-gui\error.log` (Linux: `~/.config/odx-gui/error.log`) - traceback z GUI,
  takze przy uruchomieniu przez `pythonw`.
- W podgladzie komendy pojawiaja sie linie `# ...` z ostrzezeniami
  (np. flagi bez efektu w trybie ekspresowym, niedomkniety cudzyslow).
- `_test_unifikacja.py` - test regresyjny GUI (`python3 _test_unifikacja.py`).

## Czego nie ma w repo

Pliki generowane lokalnie (sa w `.gitignore`): `_python_cache.txt`, `config.json`,
`error.log`, `run_tmp.*`, `python_path.txt`, `odx_path.txt`, `_backup/`, `__pycache__/`.
