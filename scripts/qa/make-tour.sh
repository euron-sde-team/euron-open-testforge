#!/usr/bin/env bash
# Stitch the tour frames written by screenshots.mjs into docs/assets/tour.gif.
# Each frame is held for 2.5 s; a generated palette keeps the GIF sharp and small.
# Uses a local ffmpeg when there is one, otherwise ffmpeg in a container.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRAMES="$ROOT/scripts/qa/output/tour"
OUT="$ROOT/docs/assets/tour.gif"
ls "$FRAMES"/*.png >/dev/null 2>&1 || { echo "no frames in $FRAMES: run screenshots.mjs first" >&2; exit 1; }

if command -v ffmpeg >/dev/null; then
  ff() { ffmpeg "$@"; }
  IN="$FRAMES"
  DST="$OUT"
else
  command -v docker >/dev/null || { echo "ffmpeg or docker is required" >&2; exit 1; }
  ff() { docker run --rm -v "$FRAMES:/frames" -v "$(dirname "$OUT"):/out" jrottenberg/ffmpeg:7.1-alpine "$@"; }
  IN="/frames"
  DST="/out/$(basename "$OUT")"
fi

# 1. Frames to a lossless intermediate: read at 1 fps, hold each 2.5 s, resample to a steady
#    2 fps (GIF frame differencing makes repeats nearly free). Going through a video file also
#    sidesteps a palettegen crash some ffmpeg builds hit on PNG-sequence input.
ff -y -loglevel error -framerate 1 -pattern_type glob -i "$IN/*.png" \
  -vf "setpts=2.5*PTS,fps=2,scale=1200:-1:flags=lanczos" -c:v ffv1 "$IN/tour.mkv"
# 2. Palette, then encode.
ff -y -loglevel error -i "$IN/tour.mkv" -vf "palettegen=max_colors=192" "$IN/palette.png"
ff -y -loglevel error -i "$IN/tour.mkv" -i "$IN/palette.png" \
  -lavfi "paletteuse=dither=sierra2_4a" -loop 0 "$DST"
rm -f "$FRAMES/palette.png" "$FRAMES/tour.mkv"
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
