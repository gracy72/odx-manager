# ODX Manager - jeden interfejs (Windows natywny / Debian + Docker)

Ten sam plik GUI (`gui/odx_gui.py`) dziala na obu maszynach:

| | Windows (ten katalog) | Debian 13 (kopia startera na tej maszynie) |
|---|---|---|
| silnik | natywny `run.bat` (ODX for Windows) | `docker run webodm/odx` (opcjonalnie `:gpu` + `--gpus all`) |
| wykrywanie | `_srodowisko.bat` -> `python_path.txt`, `odx_path.txt` | to samo |
| konfiguracja | `%APPDATA%\odx-gui\config.json` | `~/.config/odx-gui/config.json` |

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
- `%APPDATA%\odx-gui\error.log` - traceback z GUI (takze przy pythonw).
- W podgladzie komendy pojawiaja sie linie `# ...` z ostrzezeniami
  (np. flagi bez efektu w trybie ekspresowym, niedomkniety cudzyslow).
