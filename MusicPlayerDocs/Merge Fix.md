You’re right—you _are_ doing a TS remux + TS-concat + audio-only re-encode… but only **as a fallback** after trying MP4 concat first, and your TS path is missing a couple of flags that matter for smooth playback. Plus, your normalization still does **double FPS conversion**. Those three things together explain why only the normalized segments look choppy / silent.

Here’s what to change (surgical, minimal re-encode kept):

# 1) If the batch is mixed, **go TS first** (don’t wait for failure)

Today you pass `force_audio_remux=getattr(self, '_mixed_merge', False)` into `DouyinMergeWorker`, but still attempt MP4 concat first. Change the merge to **use the TS path immediately when `_mixed_merge` is True**, then (optionally) do the audio-only pass.

- In `_start_merging(...)`: if `getattr(self, '_mixed_merge', False)` is True, call a new `merge_via_ts_first()` (or set a flag the worker reads) so `run()` skips the MP4 concat path and jumps to `_attempt_ts_concat_fallback(...)` straight away.

# 2) Harden your **TS creation** so timestamps are clean

Your TS fallback currently creates `.ts` without resetting timestamps or regenerating PTS. Add these:
```
# per-clip TS
ffmpeg -y -hide_banner -i SRC.mp4 \
  -map 0:v:0 -map 0:a? \
  -c copy -bsf:v h264_mp4toannexb \
  -fflags +genpts -reset_timestamps 1 \
  -muxpreload 0 -muxdelay 0 \
  -f mpegts OUT.ts
```

Then concat back to MP4:
```
ffmpeg -y -hide_banner -i "concat:ONE.ts|TWO.ts|..." \
  -map 0:v:0 -map 0:a? \
  -c copy -bsf:a aac_adtstoasc -movflags +faststart OUT.mp4
```

Tweaks vs your current code:

- add `-map 0:a?` (audio optional—prevents failures on silent clips),
    
- add `-fflags +genpts -reset_timestamps 1 -muxpreload 0 -muxdelay 0` on the TS step.  
    These clear up PTS/DTS weirdness that can surface as stutter or mute starts on the re-encoded segments.
    

# 3) Fix **double FPS conversion** in normalization

Your `_NormalizeWorker` does both `-vf fps=...` **and** `-r ... -vsync cfr`. Keep exactly **one**. Easiest: drop the `fps=` filter; keep `-r {fps} -vsync cfr`.

Also remove `-force_key_frames 0` (it’s not helping and can confuse cadence). Keep your stable GOP with `-g` and `-sc_threshold 0`.

**Before (problem):**
```
-vf "fps=fps={fps},scale=... ,pad=..."
-r {fps} -vsync cfr
... -g {g_frames} -sc_threshold 0 -force_key_frames 0
```

After (clean):
```
-x264-params "keyint={g_frames}:min-keyint={g_frames}:scenecut=0:ref=3:bframes=3:b-pyramid=none"
```

# 4) Keep audio normalization simple & consistent

Your audio-only remux maps `-map 0:a:0` (hard fail if no audio). Use `-map 0:a?` and pin a single profile/rate:
```
ffmpeg -y -i merged.mp4 \
  -map 0:v:0 -map 0:a? \
  -c:v copy \
  -c:a aac -profile:a aac_low -ar 44100 -ac 2 -b:a 192k \
  -movflags +faststart merged_fix.mp4
```

This cures “silent normalized segment until next boundary” issues that happen when AAC priming / layout differs.

# 5) Make validation meaningful (optional)

Your `_validate_output()` decodes to `null`, which often **passes** even when playback is janky. Since you’ll TS-concat by policy for mixed sets, you can keep validation simple—or augment your signature probe to compare H.264 `extradata_md5` and AAC `initial_padding` to detect risky joins and force TS mode automatically.
