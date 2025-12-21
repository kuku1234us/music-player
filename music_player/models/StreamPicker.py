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
from dataclasses import dataclass, replace
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

def _norm_lang(lang: Any) -> str:
    """
    Normalize language tags like:
    - "en", "en-US", "en_US", "EN-us" -> "en-us"
    """
    s = str(lang or "").strip()
    if not s:
        return ""
    s = s.replace("_", "-").lower()
    # Collapse accidental repeats like "en--us"
    while "--" in s:
        s = s.replace("--", "-")
    return s

def _lang_match_score(candidate_lang: str, preferred_langs: tuple[str, ...]) -> int:
    """
    Returns:
    - 3 for exact match (e.g., en-us == en-us)
    - 2 for base match (e.g., en-us matches en)
    - 1 for prefix match (e.g., en matches en-us)
    - 0 for no match / unknown
    """
    c = _norm_lang(candidate_lang)
    if not c or not preferred_langs:
        return 0
    prefs = tuple(_norm_lang(x) for x in preferred_langs if x)
    if not prefs:
        return 0

    if any(c == p for p in prefs):
        return 3

    c_base = c.split("-", 1)[0]
    if any((p.split("-", 1)[0] == c_base) and (p == c_base or c == c_base) for p in prefs):
        return 2

    # Weak prefix check
    if any(c.startswith(p + "-") for p in prefs if p and "-" not in p):
        return 1
    if any(p.startswith(c + "-") for p in prefs if c and "-" not in c):
        return 1
    return 0


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
    language: str
    language_preference: Optional[int]
    audio_track_id: str
    audio_track_name: str
    audio_track_lang: str
    audio_track_is_default: bool
    audio_track_is_original: bool

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

    # If True, choose only audio formats (no video selection/merge). Useful for audio-only downloads.
    audio_only: bool = False

    # Prefer these audio languages (highest priority first). If empty, we try to infer "original/default"
    # from yt-dlp's `language_preference` / `audio_track` metadata.
    preferred_audio_languages: tuple[str, ...] = ()

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

def _audio_track_pref(c: Candidate, policy: SelectionPolicy) -> tuple:
    """
    A language/track-preference tuple that can be used both for audio-only and muxed formats.
    Higher tuple is better (lexicographic).
    """
    lang_match = _lang_match_score(c.language or c.audio_track_lang, policy.preferred_audio_languages)
    lang_pref = int(c.language_preference or 0)
    note = (c.format_note or "").lower()
    note_original = 1 if "original" in note else 0
    note_default = 1 if "default" in note else 0
    is_default_track = 1 if c.audio_track_is_default else 0
    is_original_track = 1 if c.audio_track_is_original else 0
    return (
        is_original_track,
        is_default_track,
        note_original,
        note_default,
        lang_match,
        lang_pref,
    )


def _score_audio(c: Candidate, policy: SelectionPolicy) -> tuple:
    proto = c.protocol or "unknown"
    is_preferred_proto = 1 if proto == policy.prefer_protocol else 0
    is_avoided = 1 if _is_avoided(proto, policy.avoid_protocol_prefixes) else 0
    ext_ok = 1 if (c.ext or "").lower() in policy.prefer_audio_exts else 0
    abr = c.abr or c.tbr or 0.0

    # Multi-audio handling:
    # - Prefer the "original/default" audio track when yt-dlp tells us
    # - Then apply any caller-specified/inferred language preference
    # - Prefer non-DRC when both exist (DRC tracks are typically a "normalized" variant)
    # - Then fall back to protocol/ext/bitrate
    note = (c.format_note or "").lower()
    is_drc = 1 if ("-drc" in (c.format_id or "").lower() or "drc" in note) else 0
    drc_ok = 1 if not is_drc else 0
    return _audio_track_pref(c, policy) + (
        drc_ok,
        is_preferred_proto,
        -is_avoided,
        ext_ok,
        abr,
    )


def _score_muxed(c: Candidate, policy: SelectionPolicy) -> tuple:
    """
    For muxed formats, primarily we still care about resolution/protocol/codec.
    But when multiple muxed formats are identical except the audio track (like YouTube multi-audio HLS),
    we need to prefer the original/default track.
    """
    return _score_video(c, policy) + _audio_track_pref(c, policy)


def _build_candidates(info_json: dict[str, Any]) -> list[Candidate]:
    out: list[Candidate] = []
    for f in (info_json.get("formats") or []):
        fmt_id = str(f.get("format_id") or "")
        if not fmt_id:
            continue

        # Language / multi-audio metadata (YouTube multi-audio is exposed via these fields in newer yt-dlp)
        language = _norm_lang(f.get("language"))
        language_preference = _to_int(f.get("language_preference"))
        at = f.get("audio_track")
        at_id = ""
        at_name = ""
        at_lang = ""
        at_is_default = False
        at_is_original = False
        if isinstance(at, dict):
            at_id = str(at.get("id") or "")
            # yt-dlp commonly uses display_name; keep a couple fallbacks
            at_name = str(at.get("display_name") or at.get("name") or "")
            at_lang = _norm_lang(at.get("language") or at.get("lang"))
            # These keys vary by extractor/yt-dlp version; treat missing as False
            at_is_default = bool(at.get("is_default") or at.get("default") or at.get("is_main"))
            at_is_original = bool(at.get("is_original") or at.get("original"))

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
                language=language,
                language_preference=language_preference,
                audio_track_id=at_id,
                audio_track_name=at_name,
                audio_track_lang=at_lang,
                audio_track_is_default=at_is_default,
                audio_track_is_original=at_is_original,
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
    # If the caller didn't specify preferred audio languages, try to infer a reasonable default
    # from the info JSON (useful for YouTube multi-audio where "original" often aligns with
    # the video's primary language).
    if not policy.preferred_audio_languages:
        inferred: list[str] = []
        for k in (
            "original_language",
            "default_audio_language",
            "default_language",
            "language",
            # Some sources may use camelCase-like keys
            "defaultAudioLanguage",
            "defaultLanguage",
        ):
            v = info_json.get(k)
            nl = _norm_lang(v)
            if nl:
                inferred.append(nl)
        # De-dupe while preserving order
        seen: set[str] = set()
        inferred = [x for x in inferred if not (x in seen or seen.add(x))]
        if inferred:
            policy = replace(policy, preferred_audio_languages=tuple(inferred))

    candidates = _build_candidates(info_json)
    videos = [c for c in candidates if c.is_video and not c.is_audio]  # video-only
    audios = [c for c in candidates if c.is_audio and not c.is_video]  # audio-only
    muxed = [c for c in candidates if c.is_muxed]

    chosen_video = max(videos, key=lambda x: _score_video(x, policy), default=None)
    chosen_audio = max(audios, key=lambda x: _score_audio(x, policy), default=None)
    chosen_muxed = max(muxed, key=lambda x: _score_muxed(x, policy), default=None)

    if policy.audio_only:
        # Explicit audio-only selection
        if chosen_audio:
            fmt = chosen_audio.format_id
            kind = "audio_only"
        else:
            fmt = "bestaudio"
            kind = "fallback"
    else:
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


