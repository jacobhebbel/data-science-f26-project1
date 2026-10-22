#!/usr/bin/env python3
"""
m4a_report.py - A-weighted sound level report for an .m4a recording, written in
the same CSV layout as the NIOSH SLM sound level meter export.

Usage:
    python3 m4a_report.py <path/to/file.m4a> <name_prefix> [--cal-offset DB] [--out-dir DIR]

Output: <name_prefix><created timestamp>.csv, e.g. "site3_2026-10-13_13-48-02.csv"

    Start Time: 2026-10-09 14:48:54.697      <- when the recording was made
    Export Time: 2026-10-09 14:49:36.924     <- when this report was generated
    Min (dBA): 57.6                          <- quietest 210 ms interval
    Max (dBA): 74.7                          <- loudest 210 ms interval
    Peak (dBA): 80.2                         <- highest instantaneous A-weighted peak
    Avg (dBA): 63.8                          <- Leq (energy average) of the whole file
    TWA (dBA): 0.0                           <- NIOSH 8-hour time-weighted average
    Dose (%): 0.0                            <- NIOSH noise dose

    Recorded Value (dBA),Time Stamp (yyyy-MM-dd HH:mm:ss.SSS)
    58.8,2026-10-09 14:48:58.706             <- one row per 210 ms

Levels come from the decoded audio with an IEC 61672 A-weighting curve. An
uncalibrated recording is measured relative to digital full scale (0 dBA = the
loudest signal the file can hold), so values are negative. Pass --cal-offset
(meter reading minus this script's reading for the same sound) to get dBA SPL.

TWA/Dose follow NIOSH: 85 dBA criterion, 3 dB exchange rate, 8-hour shift, and
levels below an 80 dBA threshold don't count toward dose.

Requires: Python 3.8+, numpy, and ffmpeg/ffprobe on the PATH.
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

WINDOW_SEC = 0.210          # reporting interval (matches the meter)
SAMPLE_RATE = 48000         # audio is resampled to this rate for analysis
CONTEXT_SEC = 0.250         # audio either side of each block used when filtering
FLOOR_DB = -120.0           # level reported for digital silence

# NIOSH REL dose parameters
CRITERION_DB = 85.0
EXCHANGE_DB = 3.0
THRESHOLD_DB = 80.0
SHIFT_SEC = 8 * 3600

TIME_FMT = "%Y-%m-%d %H:%M:%S.%f"


# --------------------------------------------------------------------------- #
# Audio + metadata
# --------------------------------------------------------------------------- #
def require_tools():
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        sys.exit(f"Error: {', '.join(missing)} not found on PATH. Install ffmpeg first.")


def probe(path):
    """Return ffprobe's format/stream metadata as a dict."""
    cmd = ["ffprobe", "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"Error: ffprobe could not read '{path}':\n{res.stderr.strip()}")
    return json.loads(res.stdout)


def parse_iso(ts):
    """Parse ffprobe's creation_time (e.g. '2026-10-13T17:48:02.000000Z')."""
    ts = ts.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        # Trim fractional seconds that Python < 3.11 can't handle
        if "." not in ts:
            raise
        head, tail = ts.split(".", 1)
        tz = ""
        for sep in ("+", "-"):
            if sep in tail:
                tz = sep + tail.split(sep, 1)[1]
                break
        dt = datetime.fromisoformat(head + tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def file_created_time(path, meta):
    """
    When was the recording made? Prefer the creation_time tag the recorder
    wrote into the m4a (survives copying/emailing); fall back to the
    filesystem's creation (birth) time, then to modification time.
    Returns (local datetime, source description).
    """
    tags = dict(meta.get("format", {}).get("tags", {}))
    for s in meta.get("streams", []):
        for k, v in s.get("tags", {}).items():
            tags.setdefault(k, v)
    for key in ("creation_time", "com.apple.quicktime.creationdate", "date"):
        for k, v in tags.items():
            if k.lower() == key:
                try:
                    return parse_iso(v).astimezone(), f"m4a metadata ({k})"
                except ValueError:
                    pass

    st = os.stat(path)
    birth = getattr(st, "st_birthtime", None)       # macOS / Windows (py3.12+)
    if birth:
        return datetime.fromtimestamp(birth).astimezone(), "filesystem creation time"
    return datetime.fromtimestamp(st.st_mtime).astimezone(), \
        "filesystem modification time (creation time unavailable)"


def decode_mono(path, sr=SAMPLE_RATE):
    """Decode any audio file to a mono float32 numpy array in [-1, 1]."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vn",
           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        sys.exit(f"Error: ffmpeg could not decode '{path}':\n{res.stderr.decode().strip()}")
    audio = np.frombuffer(res.stdout, dtype=np.float32)
    if audio.size == 0:
        sys.exit(f"Error: no audio found in '{path}'.")
    return audio


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def a_weighting_gain(freqs):
    """Linear A-weighting gain (IEC 61672-1) at each frequency in Hz."""
    f2 = np.asarray(freqs, dtype=np.float64) ** 2
    num = (12194.0 ** 2) * f2 ** 2
    den = ((f2 + 20.6 ** 2)
           * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
           * (f2 + 12194.0 ** 2))
    with np.errstate(divide="ignore", invalid="ignore"):
        ra = np.where(den > 0, num / den, 0.0)
    return ra * 10 ** (2.0 / 20.0)      # +2.00 dB normalises to 0 dB at 1 kHz


def to_db(x):
    return 10 * math.log10(x) if x > 0 else FLOOR_DB


def analyse(audio, sr=SAMPLE_RATE, window_sec=WINDOW_SEC):
    """
    A-weight the audio and split it into consecutive 210 ms blocks.
    Returns (per-block levels in dB, per-block mean squares, overall peak in dB,
    block length in samples). Levels are relative to full scale (uncalibrated).

    Each block is filtered together with CONTEXT_SEC of surrounding audio so
    the A-weighting filter isn't distorted at block edges, and memory use stays
    flat for long recordings.
    """
    n = int(round(sr * window_sec))
    ctx = int(round(sr * CONTEXT_SEC))
    seg_len = n + 2 * ctx
    gain = a_weighting_gain(np.fft.rfftfreq(seg_len, d=1.0 / sr))
    padded = np.pad(audio.astype(np.float64), (ctx, ctx + n))

    levels, mean_squares, peak = [], [], 0.0
    for start in range(0, audio.size, n):
        valid = min(n, audio.size - start)
        if valid < n // 2 and levels:      # skip tiny trailing scrap (encoder padding)
            break
        seg = padded[start:start + seg_len]
        weighted = np.fft.irfft(np.fft.rfft(seg) * gain, seg_len)[ctx:ctx + valid]
        ms = float(np.mean(weighted ** 2))
        levels.append(to_db(ms))
        mean_squares.append(ms)
        peak = max(peak, float(np.max(np.abs(weighted))))
    return levels, mean_squares, to_db(peak ** 2), n


def niosh_dose_twa(levels, interval_sec):
    """NIOSH noise dose (%) and 8-hour TWA (dBA) from per-interval levels."""
    dose = 0.0
    for lvl in levels:
        if lvl >= THRESHOLD_DB:
            allowed = SHIFT_SEC / 2 ** ((lvl - CRITERION_DB) / EXCHANGE_DB)
            dose += interval_sec / allowed
    dose *= 100.0
    twa = CRITERION_DB + EXCHANGE_DB / math.log10(2) * math.log10(dose / 100.0) \
        if dose > 0 else 0.0
    return dose, twa


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def fmt_time(dt):
    """yyyy-MM-dd HH:mm:ss.SSS in local time, like the meter export."""
    return dt.strftime(TIME_FMT)[:-3]


def write_report(out_path, created, levels, mean_squares, peak_db, interval_sec, cal):
    lv = [l + cal for l in levels]
    leq = to_db(float(np.mean(mean_squares))) + cal
    dose, twa = niosh_dose_twa(lv, interval_sec)
    start = created.replace(tzinfo=None)

    lines = [
        f"Start Time: {fmt_time(start)}",
        f"Export Time: {fmt_time(datetime.now())}",
        f"Min (dBA): {min(lv):.1f}",
        f"Max (dBA): {max(lv):.1f}",
        f"Peak (dBA): {peak_db + cal:.1f}",
        f"Avg (dBA): {leq:.1f}",
        f"TWA (dBA): {twa:.1f}",
        f"Dose (%): {dose:.1f}",
        "",
        "Recorded Value (dBA),Time Stamp (yyyy-MM-dd HH:mm:ss.SSS)",
    ]
    # Each value is stamped at the end of its 210 ms interval, as a meter does
    for i, lvl in enumerate(lv):
        stamp = start + timedelta(seconds=(i + 1) * interval_sec)
        lines.append(f"{lvl:.1f},{fmt_time(stamp)}")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return lv, leq


def main():
    ap = argparse.ArgumentParser(
        description="Report A-weighted levels (dBA) every 210 ms for an .m4a file.")
    ap.add_argument("file", help="path to the .m4a file")
    ap.add_argument("prefix", help="name prefix for the output CSV")
    ap.add_argument("--cal-offset", type=float, default=0.0,
                    help="dB added to every level to convert full-scale dBA to dBA SPL")
    ap.add_argument("--out-dir", default=".",
                    help="folder to save the CSV in (default: current folder)")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        sys.exit(f"Error: file not found: {args.file}")
    require_tools()

    meta = probe(args.file)
    created, created_src = file_created_time(args.file, meta)
    audio = decode_mono(args.file)
    levels, mean_squares, peak_db, n = analyse(audio)

    os.makedirs(args.out_dir, exist_ok=True)
    out_name = f"{args.prefix}{created.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    out_path = os.path.join(args.out_dir, out_name)
    lv, leq = write_report(out_path, created, levels, mean_squares, peak_db,
                           n / SAMPLE_RATE, args.cal_offset)

    print(f"Start time: {fmt_time(created)} (from {created_src})")
    print(f"{len(lv)} intervals | min {min(lv):.1f} / max {max(lv):.1f} / "
          f"median {float(np.median(lv)):.1f} / avg (Leq) {leq:.1f} dBA")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
