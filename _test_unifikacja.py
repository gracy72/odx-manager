# -*- coding: utf-8 -*-
"""Test zgodnosci GUI po unifikacji (5490): katalog, presety, wlasne flagi."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "gui"))
import odx_gui as g

fails = []


def check(label, cond, extra=""):
    print(("[OK]   " if cond else "[FAIL] ") + label + ("  " + extra if extra else ""))
    if not cond:
        fails.append(label)


app = g.ODXForm()
app.update()

cat = {f for _, f in g.BOOL_FLAGS} | {o[1] for o in g.VALUE_OPTS}
print("katalog dodatkowy:", len(g.BOOL_FLAGS), "bool +", len(g.VALUE_OPTS), "z wartoscia,"
      " razem flag:", len(cat))
check("widgety nowych grup", all(k in app._chk_more for k in
      ("use_exif", "sfm_no_partial", "hybrid_ba", "sm_no_align",
       "pc_skip_geom", "tex_skip_seam", "tex_keep_unseen", "tex_single_mat",
       "skip_band_align")))
check("pola nowych grup", all(k in app._ent_more for k in
      ("boundary", "geo", "align", "copy_to", "matcher_neighbors",
       "gps_z_offset", "primary_band", "split", "split_overlap",
       "smrf_window", "dem_gapfill")))
check("listy nowych grup", "radiometric" in app._cmb_more)
check("pole wlasnych flag", hasattr(app, "edt_extra"))

app.edt_folder.delete(0, "end")
app.edt_folder.insert(0, r"C:\Users\g.blachowicz\Temp\odxtest\dzialka")

app.apply_night_preset()
night = app.memo.get("1.0", "end").strip().replace("\n", " ")
app.apply_express_preset()
express = app.memo.get("1.0", "end").strip().replace("\n", " ")
print("\nNIGHT  :", night[-230:])
print("EXPRESS:", express[-230:])
check("ekspres: fast-ortho", "--fast-orthophoto" in express)
check("ekspres: bez --rerun-all", "--rerun-all" not in express)
check("ekspres: orto 2.0", "--orthophoto-resolution 2.0" in express)
check("ekspres: bez --dsm/--dtm", "--dsm" not in express and "--dtm" not in express)
check("ekspres: bez --dem-resolution", "--dem-resolution" not in express)

# wlasne flagi + nowe opcje
app.edt_extra.insert("1.0", '--min-num-features 30000 --boundary "C:\\projekty\\a.geojson"')
app._chk_more["use_exif"].var.set(True)
app._ent_more["split"].delete(0, "end")
app._ent_more["split"].insert(0, "300")
app._ent_more["smrf_window"].delete(0, "end")
app._ent_more["smrf_window"].insert(0, "25")
app.update_all()
cmd = app.memo.get("1.0", "end").strip().replace("\n", " ")
print("\nMANUAL :", cmd[-330:])
check("wlasne flagi w komendzie", "--min-num-features 30000" in cmd)
check("cudzyslow zachowany", 'a.geojson' in cmd)
check("--use-exif", "--use-exif" in cmd)
check("--split 300", "--split 300" in cmd)
check("--smrf-window tylko z DEM", "--smrf-window" not in cmd)  # DEM wylaczony w ekspresie

# notka o fladze bez efektu
app._chk_more["pc_las"].var.set(True)
app.update_all()
preview = app.memo.get("1.0", "end").strip()
check("notka o pc-las w trybie ekspresowym", "ignorowane" in preview)

# bez DEM nie ma tez smrf -> sprawdz z DEM
app.apply_night_preset()
app._ent_more["smrf_window"].delete(0, "end")
app._ent_more["smrf_window"].insert(0, "25")
app.update_all()
cmd2 = app.memo.get("1.0", "end").strip().replace("\n", " ")
check("--smrf-window z --dtm", "--smrf-window 25" in cmd2, cmd2[-200:])

# CLI zgodne z run.py
check("CLI: nazwa + --project-path",
      "run.bat dzialka --project-path" in cmd2.replace("\\", "/").replace("/", "\\"))

app.destroy()
print("\nbledy:", len(fails), fails if fails else "")
sys.exit(1 if fails else 0)
