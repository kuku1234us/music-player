"""
StreamPicker
------------

Deterministically selects yt-dlp format IDs (e.g. "298+140") using a *no-cookies* probe.

Why:
- `yt-dlp -F` (listing) may show more formats than an actual download.
- But we want a stable, explicit selection step that prefers HTTPS at the correct
  resolution (avoid m3u8 unless needed), then perform the actual download with
  cookies + JS runtime.

This module uses `yt-dlp --skip-download --dump-single-json` (no cookies) to obtain
the same formats list that `-F` prints, but in a machine-parseable way.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Optional


def _windows_no_window_flag() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def _to_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _norm_proto(p: Any) -> str:
    return str(p or "").lower() or "unknown"


@dataclass(frozen=True)
class Candidate:
    format_id: str
    protocol: str
    ext: str
    vcodec: str
    acodec: str
    height: Optional[int]
    width: Optional[int]
    fps: Optional[float]
    tbr: Optional[float]
    abr: Optional[float]
    format_note: str

    @property
    def is_video(self) -> bool:
        v = (self.vcodec or "").lower()
        return v not in ("none", "null", "")

    @property
    def is_audio(self) -> bool:
        a = (self.acodec or "").lower()
        return a not in ("none", "null", "")

    @property
    def is_muxed(self) -> bool:
        return self.is_video and self.is_audio


@dataclass(frozen=True)
class SelectionPolicy:
    # If target_height is None => "best" mode (max quality, still prefer https).
    target_height: Optional[int]
    # For portrait videos: if candidate is portrait, we treat "target" as width instead of height.
    target_width: Optional[int]

    prefer_protocol: str = "https"
    avoid_protocol_prefixes: tuple[str, ...] = ("m3u8",)

    prefer_video_exts: tuple[str, ...] = ("mp4",)
    prefer_audio_exts: tuple[str, ...] = ("m4a",)
    prefer_vcodec_prefixes: tuple[str, ...] = ("avc", "h264")

    # If True, https beats resolution. If False, resolution beats protocol.
    prefer_protocol_over_resolution: bool = False


@dataclass(frozen=True)
class PickResult:
    format_spec: str
    chosen_kind: str  # video+audio | muxed | audio_only | fallback
    chosen_video_id: Optional[str]
    chosen_audio_id: Optional[str]
    chosen_muxed_id: Optional[str]
    debug: dict[str, Any]


def _is_avoided(proto: str, prefixes: tuple[str, ...]) -> bool:
    p = (proto or "").lower()
    return any(p.startswith(x) for x in prefixes)


def _score_video(c: Candidate, policy: SelectionPolicy) -> tuple:
    """
    Higher tuple is better (lexicographic).
    """
    proto = c.protocol or "unknown"
    is_preferred_proto = 1 if proto == policy.prefer_protocol else 0
    is_avoided = 1 if _is_avoided(proto, policy.avoid_protocol_prefixes) else 0

    vcodec = (c.vcodec or "").lower()
    vcodec_ok = 1 if any(vcodec.startswith(p) for p in policy.prefer_vcodec_prefixes) else 0
    ext_ok = 1 if (c.ext or "").lower() in policy.prefer_video_exts else 0

    fps = c.fps or 0.0
    tbr = c.tbr or 0.0

    # "Best" mode: prefer https, then bitrate/fps, then preferences.
    if policy.target_height is None:
        return (is_preferred_proto, -is_avoided, vcodec_ok, ext_ok, fps, tbr)

    target_h = policy.target_height
    target_w = policy.target_width

    # Portrait-aware "effective" dimension matching
    is_portrait = bool(c.width and c.height and c.height > c.width)
    if is_portrait and target_w is not None and c.width is not None:
        eff = c.width
        target = target_w
    else:
        eff = c.height
        target = target_h

    # Bucket: exact match > below target > unknown > above target
    if eff is None:
        res_bucket = 1
        res_distance = 9999
    else:
        if eff == target:
            res_bucket = 4
            res_distance = 0
        elif eff < target:
            res_bucket = 3
            res_distance = target - eff
        else:
            res_bucket = 0
            res_distance = eff - target

    if policy.prefer_protocol_over_resolution:
        return (
            is_preferred_proto,
            -is_avoided,
            res_bucket,
            -res_distance,
            vcodec_ok,
            ext_ok,
            fps,
            tbr,
        )
    return (
        res_bucket,
        -res_distance,
        is_preferred_proto,
        -is_avoided,
        vcodec_ok,
        ext_ok,
        fps,
        tbr,
    )


def _score_audio(c: Candidate, policy: SelectionPolicy) -> tuple:
    proto = c.protocol or "unknown"
    is_preferred_proto = 1 if proto == policy.prefer_protocol else 0
    is_avoided = 1 if _is_avoided(proto, policy.avoid_protocol_prefixes) else 0
    ext_ok = 1 if (c.ext or "").lower() in policy.prefer_audio_exts else 0
    abr = c.abr or c.tbr or 0.0
    return (is_preferred_proto, -is_avoided, ext_ok, abr)


def _build_candidates(info_json: dict[str, Any]) -> list[Candidate]:
    out: list[Candidate] = []
    for f in (info_json.get("formats") or []):
        fmt_id = str(f.get("format_id") or "")
        if not fmt_id:
            continue
        out.append(
            Candidate(
                format_id=fmt_id,
                protocol=_norm_proto(f.get("protocol")),
                ext=str(f.get("ext") or ""),
                vcodec=str(f.get("vcodec") or "none"),
                acodec=str(f.get("acodec") or "none"),
                height=_to_int(f.get("height")),
                width=_to_int(f.get("width")),
                fps=_to_float(f.get("fps")),
                tbr=_to_float(f.get("tbr")),
                abr=_to_float(f.get("abr")),
                format_note=str(f.get("format_note") or ""),
            )
        )
    return out


def probe_formats_json(
    *,
    ytdlp_path: str,
    url: str,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """
    Probe *without cookies* (intentionally) to mimic a clean `yt-dlp -F URL` listing step.
    """
    cmd = [ytdlp_path, "--no-playlist", "--skip-download", "--dump-single-json", url]
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        creationflags=_windows_no_window_flag(),
    )
    if p.returncode != 0:
        raise RuntimeError(f"yt-dlp probe failed (rc={p.returncode}): {p.stderr.strip()}")
    try:
        return json.loads(p.stdout)
    except Exception as e:
        raise RuntimeError(f"yt-dlp probe JSON parse failed: {e}")


def pick_from_info_json(info_json: dict[str, Any], policy: SelectionPolicy) -> PickResult:
    candidates = _build_candidates(info_json)
    videos = [c for c in candidates if c.is_video and not c.is_audio]  # video-only
    audios = [c for c in candidates if c.is_audio and not c.is_video]  # audio-only
    muxed = [c for c in candidates if c.is_muxed]

    chosen_video = max(videos, key=lambda x: _score_video(x, policy), default=None)
    chosen_audio = max(audios, key=lambda x: _score_audio(x, policy), default=None)
    chosen_muxed = max(muxed, key=lambda x: _score_video(x, policy), default=None)

    if policy.target_height is None and not videos and muxed:
        # In "best" mode, muxed might be the only thing available
        pass

    if policy.target_height is None and chosen_video and chosen_audio:
        fmt = f"{chosen_video.format_id}+{chosen_audio.format_id}"
        kind = "video+audio"
    elif policy.target_height is None and chosen_muxed:
        fmt = chosen_muxed.format_id
        kind = "muxed"
    else:
        # Resolution constrained: prefer video+audio, else muxed, else audio-only, else fallback.
        if chosen_video and chosen_audio:
            fmt = f"{chosen_video.format_id}+{chosen_audio.format_id}"
            kind = "video+audio"
        elif chosen_muxed:
            fmt = chosen_muxed.format_id
            kind = "muxed"
        elif chosen_audio:
            fmt = chosen_audio.format_id
            kind = "audio_only"
        else:
            fmt = "best"
            kind = "fallback"

    debug = {
        "counts": {"total": len(candidates), "video_only": len(videos), "audio_only": len(audios), "muxed": len(muxed)},
        "policy": policy.__dict__,
    }

    return PickResult(
        format_spec=fmt,
        chosen_kind=kind,
        chosen_video_id=(chosen_video.format_id if chosen_video else None),
        chosen_audio_id=(chosen_audio.format_id if chosen_audio else None),
        chosen_muxed_id=(chosen_muxed.format_id if chosen_muxed else None),
        debug=debug,
    )


def pick_for_url(
    *,
    ytdlp_path: str,
    url: str,
    policy: SelectionPolicy,
    timeout_s: int = 120,
) -> PickResult:
    info = probe_formats_json(ytdlp_path=ytdlp_path, url=url, timeout_s=timeout_s)
    return pick_from_info_json(info, policy)


