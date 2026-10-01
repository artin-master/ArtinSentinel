#!/usr/bin/env python3
"""Exercise the local FFmpeg video path without contacting a recorder."""

import argparse
import re
import shutil
import subprocess
import sys


def run(*args: str, timeout: float = 8) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_media() -> list[tuple[str, bool]]:
    results = [(name, shutil.which(name) is not None)
               for name in ("ffmpeg", "ffprobe", "ffplay")]
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        probe = run(ffmpeg, "-hide_banner", "-decoders")
        decoders = set(re.findall(rb"^\s*[A-Z.]{6}\s+([A-Za-z0-9_-]+)\s",
                                  probe.stdout, re.MULTILINE)) if probe and probe.returncode == 0 else set()
        results.extend((f"decoder {codec.decode()}", codec in decoders)
                       for codec in (b"h264", b"hevc"))
        frame = run(ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=16x16:r=1",
                    "-vf", "scale=16:16", "-frames:v", "1", "-pix_fmt", "rgb24",
                    "-f", "rawvideo", "pipe:1")
        results.append(("quadro RGB24", bool(frame and frame.returncode == 0
                                              and len(frame.stdout) == 16 * 16 * 3)))
    if ffprobe := shutil.which("ffprobe"):
        probe = run(ffprobe, "-hide_banner", "-h", "demuxer=rtsp")
        results.append(("RTSP ffprobe", bool(probe and probe.returncode == 0
                                               and b"Demuxer rtsp" in probe.stdout + probe.stderr)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    results = check_media()
    if not args.quiet:
        for name, ok in results:
            print(f"  {name:16} {'OK' if ok else 'FALTA [essencial]'}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
