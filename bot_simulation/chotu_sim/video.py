"""MP4 writer: H.264 through the ffmpeg CLI when available, OpenCV fallback."""
from __future__ import annotations

import shutil
import subprocess

import cv2
import numpy as np


class VideoWriter:
    def __init__(self, path: str, fps: int, size=(1280, 720), crf: int = 24):
        self.path = path
        self.size = size
        self.proc = None
        self.cv = None
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            self.proc = subprocess.Popen(
                [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                 "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", path],
                stdin=subprocess.PIPE)
        else:
            self.cv = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)

    def write(self, frame: np.ndarray) -> None:
        if self.proc:
            self.proc.stdin.write(frame.tobytes())
        else:
            self.cv.write(frame)

    def close(self) -> None:
        if self.proc:
            self.proc.stdin.close()
            self.proc.wait()
        elif self.cv:
            self.cv.release()
