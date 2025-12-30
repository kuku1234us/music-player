"""
VLC backend implementation using a Multi-Threaded, Double-Buffered architecture.
Each media playback session runs in its own dedicated thread to ensure UI responsiveness
during transitions, isolating the blocking vlc.stop() calls.
"""
import os
import sys
import vlc
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread, pyqtSlot, QMetaObject, Qt
from qt_base_app.models.logger import Logger
from .windows_path_utils import resolve_mapped_drive_to_unc

# Default VLC arguments for hardware acceleration and performance
VLC_ARGS = [
    "--no-video-title-show",
    "--avcodec-hw=any",
    "--vout=directdraw",
    "--avcodec-fast",
    "--intf=dummy",
    "--no-stats",
    "--network-caching=1000",
    "--file-caching=300",
    "--quiet"
]

class VLCWorker(QObject):
    """
    Worker that handles a single VLC instance/media session in a separate thread.
    """
    state_changed = pyqtSignal(str)   
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    media_loaded = pyqtSignal(dict, bool, list, list) # metadata, is_video, audio_tracks, sub_tracks
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)
    sig_done = pyqtSignal()
    # Stop command signal (queued across threads). Safer than string-based invokeMethod.
    sig_stop_command = pyqtSignal()

    def __init__(self, name, surface_id, media_path):
        super().__init__()
        self.name = name
        self.surface_id = surface_id
        self.media_path = media_path
        
        self.instance = None
        self.player = None
        self.media = None
        self._is_stopping = False
        self._ignore_end_reached = False
        self.timer = None  # legacy (we no longer poll position via QTimer)
        self._event_manager = None
        self._cb_time_changed = None
        self._cb_end_reached = None
        self._cb_error = None

        # Ensure stop requests are delivered to the worker thread reliably
        self.sig_stop_command.connect(self.stop_and_cleanup)
        
    @pyqtSlot()
    def initialize_and_play(self):
        Logger.instance().debug(caller="VLCWorker", msg=f"[{self.name}] Initializing for: {self.media_path}")
        try:
            self.instance = vlc.Instance(VLC_ARGS)
            self.player = self.instance.media_player_new()

            # Defensive defaults: ensure audio is enabled/unmuted at session start.
            try:
                self.player.audio_set_mute(False)
            except Exception:
                pass
            try:
                # Some VLC builds can start muted/0-volume depending on last session.
                self.player.audio_set_volume(100)
            except Exception:
                pass
            
            if sys.platform == "win32" and self.surface_id:
                self.player.set_hwnd(self.surface_id)
                try:
                    self.player.video_set_mouse_input(False)
                    self.player.video_set_key_input(False)
                except Exception:
                    pass
            
            self.media = self.instance.media_new(self.media_path)
            self.player.set_media(self.media)

            # IMPORTANT: Use libVLC events instead of polling get_state()/get_time() on a QTimer.
            # Rationale:
            # - In production we observed "ghost audio" where old sessions keep playing.
            # - The main difference vs `vlc_test_ab.py` is our periodic polling (_update_position).
            # - If a libVLC call inside the poller blocks, the worker thread event loop stalls,
            #   and queued stop commands can't run -> old audio continues until natural end.
            # Event callbacks run on libVLC internal threads and do not block the worker's event loop,
            # which keeps stop commands responsive.
            try:
                self._event_manager = self.player.event_manager()

                def _on_time_changed(event):
                    if self._is_stopping or not self.player:
                        return
                    try:
                        t = self.player.get_time()
                    except Exception:
                        return
                    if t is not None and t >= 0:
                        self.position_changed.emit(int(t))

                def _on_end(event):
                    if self._is_stopping:
                        return
                    if self._ignore_end_reached:
                        return
                    Logger.instance().debug(caller="VLCWorker", msg=f"[{self.name}] End reached (event)")
                    self.end_reached.emit()

                def _on_err(event):
                    if self._is_stopping:
                        return
                    self.error_occurred.emit("VLC Error State")

                self._cb_time_changed = _on_time_changed
                self._cb_end_reached = _on_end
                self._cb_error = _on_err

                self._event_manager.event_attach(vlc.EventType.MediaPlayerTimeChanged, self._cb_time_changed)
                self._event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._cb_end_reached)
                self._event_manager.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._cb_error)
            except Exception as e:
                Logger.instance().warning(caller="VLCWorker", msg=f"[{self.name}] Event attach warning: {e}")
            
            if self.player.play() == -1:
                self.error_occurred.emit("Failed to start playback")
                return

            self.state_changed.emit("playing")
            
            # Delay metadata parsing to allow VLC to read headers
            QTimer.singleShot(300, self._parse_metadata)

        except Exception as e:
            Logger.instance().error(caller="VLCWorker", msg=f"[{self.name}] Init Error: {e}")
            self.error_occurred.emit(str(e))

    def _parse_metadata(self):
        if not self.player or not self.media or self._is_stopping:
            return

        if self.media.get_parsed_status() != vlc.MediaParsedStatus.done:
             self.media.parse_with_options(vlc.MediaParseFlag.local, -1)

        is_video = False
        audio_tracks = []
        subtitle_tracks = []

        try:
            # Video Detection
            track_count = self.player.video_get_track_count()
            if track_count is not None and track_count > 0:
                is_video = True
            
            # Audio Tracks
            # Note: VLC APIs might return bytes, need decoding
            a_desc = self.player.audio_get_track_description()
            if a_desc:
                for tid, tname in a_desc:
                    name_str = tname.decode('utf-8', 'ignore') if isinstance(tname, bytes) else str(tname)
                    audio_tracks.append({'id': tid, 'name': name_str})

            # Subtitle Tracks
            s_desc = self.player.video_get_spu_description()
            if s_desc:
                for tid, tname in s_desc:
                    name_str = tname.decode('utf-8', 'ignore') if isinstance(tname, bytes) else str(tname)
                    # Try to get language if possible (advanced)
                    lang = ""
                    # try: lang = self.player.video_get_spu_language(tid)
                    # except: pass
                    subtitle_tracks.append({
                        'id': tid, 
                        'name': tname, # keep original bytes for compatibility?
                        'display_name': name_str,
                        'language': lang
                    })

        except Exception as e:
            Logger.instance().warning(caller="VLCWorker", msg=f"Metadata parse warning: {e}")

        mrl = self.media.get_mrl() or ""
        basename = os.path.basename(self.media_path)
        
        metadata = {
            'title': self.media.get_meta(vlc.Meta.Title) or basename,
            'artist': self.media.get_meta(vlc.Meta.Artist) or "Unknown Artist",
            'album': self.media.get_meta(vlc.Meta.Album) or "Unknown Album",
            'duration': self.player.get_length(),
            'artwork_path': None 
        }
        
        # Emit all data at once
        self.media_loaded.emit(metadata, is_video, audio_tracks, subtitle_tracks)
        self.duration_changed.emit(metadata['duration'])

    def _update_position(self):
        if not self.player or self._is_stopping:
            return
        state = self.player.get_state()
        # Logger.instance().debug(caller="VLCWorker", msg=f"[{self.name}] State: {state}")
        
        if self._ignore_end_reached:
            if state in (vlc.State.Playing, vlc.State.Buffering, vlc.State.Opening):
                self._ignore_end_reached = False
            elif state in (vlc.State.Ended, vlc.State.Stopped):
                return
        
        if state == vlc.State.Ended or state == vlc.State.Stopped:
            Logger.instance().debug(caller="VLCWorker", msg=f"[{self.name}] End reached (State: {state})")
            self.end_reached.emit()
            if self.timer:
                self.timer.stop()
        elif state == vlc.State.Error:
            self.error_occurred.emit("VLC Error State")
        elif state in (vlc.State.Playing, vlc.State.Paused):
            pos = self.player.get_time()
            if pos >= 0:
                self.position_changed.emit(pos)

    @pyqtSlot()
    def play(self):
        if self.player: 
            Logger.instance().debug(caller="VLCWorker", msg=f"[{self.name}] Play requested")
            
            # Ensure we restart from beginning if ended/stopped
            current_state = self.player.get_state()
            if current_state in (vlc.State.Ended, vlc.State.Stopped):
                 Logger.instance().debug(caller="VLCWorker", msg=f"[{self.name}] Restarting from End/Stop (seek-to-0)")
                 self._ignore_end_reached = True
                 # Prefer a rewind over stop(): stop() can detach vout and trigger VLC popup windows.
                 try:
                     self.player.set_time(0)
                 except Exception:
                     pass
                 try:
                     self.player.set_position(0.0)
                 except Exception:
                     pass
                 
            self.player.play()
            self.state_changed.emit("playing")

    @pyqtSlot()
    def pause(self):
        if self.player: 
            self.player.set_pause(1)
            self.state_changed.emit("paused")

    @pyqtSlot(int)
    def seek(self, pos):
        if not self.player or self._is_stopping:
            return

        try:
            target = int(pos)
        except Exception:
            return

        try:
            state = self.player.get_state()
        except Exception:
            state = None

        # libVLC often ignores set_time() when the player is in Ended/Stopped/Error.
        # Our old single-thread backend handled this by doing a tiny reset cycle
        # (stop -> play -> pause) before seeking. We replicate that here.
        if state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
            self._ignore_end_reached = True
            try:
                # Reset playback state so seeking works again
                self.player.stop()

                # Re-assert video output window handle to prevent VLC from creating a popup window
                if sys.platform == "win32" and self.surface_id:
                    try:
                        self.player.set_hwnd(self.surface_id)
                        self.player.video_set_mouse_input(False)
                        self.player.video_set_key_input(False)
                    except Exception:
                        pass

                # Re-assert media object (defensive)
                if self.media:
                    try:
                        self.player.set_media(self.media)
                    except Exception:
                        pass

                # Kick VLC out of Ended/Stopped so set_time() is honored
                try:
                    self.player.play()
                except Exception:
                    pass
                try:
                    self.player.set_pause(1)
                except Exception:
                    pass
            except Exception:
                # If reset fails, still attempt to seek below
                pass

        try:
            self.player.set_time(target)
        except Exception:
            pass

    @pyqtSlot(int)
    def set_volume(self, vol):
        if self.player: self.player.audio_set_volume(vol)
        
    @pyqtSlot(float)
    def set_rate(self, rate):
        if self.player: self.player.set_rate(rate)

    @pyqtSlot(int)
    def set_audio_track(self, track_id):
        if self.player: self.player.audio_set_track(track_id)

    @pyqtSlot(int)
    def set_subtitle_track(self, track_id):
        if self.player: self.player.video_set_spu(track_id)

    @pyqtSlot()
    def stop_and_cleanup(self):
        Logger.instance().debug(caller="VLCWorker", msg=f"[{self.name}] Stopping... (This may block)")
        self._is_stopping = True
        try:
            # Detach VLC event callbacks first to prevent post-release callbacks.
            try:
                if self._event_manager and self._cb_time_changed:
                    self._event_manager.event_detach(vlc.EventType.MediaPlayerTimeChanged, self._cb_time_changed)
                if self._event_manager and self._cb_end_reached:
                    self._event_manager.event_detach(vlc.EventType.MediaPlayerEndReached, self._cb_end_reached)
                if self._event_manager and self._cb_error:
                    self._event_manager.event_detach(vlc.EventType.MediaPlayerEncounteredError, self._cb_error)
            except Exception:
                pass
            self._event_manager = None
            self._cb_time_changed = None
            self._cb_end_reached = None
            self._cb_error = None

            if self.player:
                # Best-effort: stop audio ASAP even if stop() blocks in libVLC
                try:
                    self.player.audio_set_mute(True)
                except Exception:
                    pass
                try:
                    self.player.audio_set_volume(0)
                except Exception:
                    pass
                try:
                    self.player.set_pause(1)
                except Exception:
                    pass

                try:
                    self.player.stop()
                except Exception as e:
                    Logger.instance().warning(caller="VLCWorker", msg=f"[{self.name}] stop() raised: {e}")

                try:
                    self.player.release()
                except Exception:
                    pass
                self.player = None

            if self.instance:
                try:
                    self.instance.release()
                except Exception:
                    pass
                self.instance = None
        finally:
            Logger.instance().debug(caller="VLCWorker", msg=f"[{self.name}] Cleanup finished.")
            self.sig_done.emit()

class VLCBackend(QObject):
    media_loaded = pyqtSignal(dict, bool)
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    state_changed = pyqtSignal(str)
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)
    # Emitted when an old worker/thread has fully finished and its video surface can be released.
    surface_released = pyqtSignal(int)

    _sig_worker_play = pyqtSignal()
    _sig_worker_pause = pyqtSignal()
    _sig_worker_seek = pyqtSignal(int)
    _sig_worker_set_vol = pyqtSignal(int)
    _sig_worker_set_rate = pyqtSignal(float)
    _sig_worker_set_audio = pyqtSignal(int)
    _sig_worker_set_spu = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_position = 0
        self._current_duration = 0
        self._current_volume = 100
        self._current_rate = 1.0
        self._is_playing = False
        self._current_media_path = None
        self._hwnd = None 
        
        # Track Caches
        self._cached_audio_tracks = []
        self._cached_subtitle_tracks = []

        self.active_worker = None
        self.active_thread = None
        self.worker_counter = 0
        self.zombie_threads = [] 

    def _disconnect_all_worker_control_signals(self):
        """
        Defensive: ensure control signals are only connected to the current active worker.
        If a disconnect ever fails, old workers might still receive play/pause/etc and
        you can get overlapping audio.
        """
        for sig in (
            self._sig_worker_play,
            self._sig_worker_pause,
            self._sig_worker_seek,
            self._sig_worker_set_vol,
            self._sig_worker_set_rate,
            self._sig_worker_set_audio,
            self._sig_worker_set_spu,
        ):
            try:
                sig.disconnect()
            except TypeError:
                # No connections
                pass
            except Exception:
                pass

    def load_media(self, media_path, hwnd=None):
        if not os.path.exists(media_path):
            self.error_occurred.emit(f"File not found: {media_path}")
            return False

        if hwnd is not None:
            self._hwnd = hwnd

        self.worker_counter += 1
        worker_name = f"Worker_{self.worker_counter}"
        Logger.instance().info(caller="VLCBackend", msg=f"Switching to {worker_name} for: {os.path.basename(media_path)}")

        if self.active_worker:
            self._retire_active_worker()

        # Reset caches
        self._cached_audio_tracks = []
        self._cached_subtitle_tracks = []

        # Make absolutely sure we don't have stale signal connections
        self._disconnect_all_worker_control_signals()

        thread = QThread()
        worker = VLCWorker(worker_name, self._hwnd, media_path)
        worker.moveToThread(thread)
        
        self._sig_worker_play.connect(worker.play)
        self._sig_worker_pause.connect(worker.pause)
        self._sig_worker_seek.connect(worker.seek)
        self._sig_worker_set_vol.connect(worker.set_volume)
        self._sig_worker_set_rate.connect(worker.set_rate)
        self._sig_worker_set_audio.connect(worker.set_audio_track)
        self._sig_worker_set_spu.connect(worker.set_subtitle_track)
        
        worker.state_changed.connect(self._on_worker_state_changed)
        worker.position_changed.connect(self._on_worker_position_changed)
        worker.duration_changed.connect(self._on_worker_duration_changed)
        worker.media_loaded.connect(self._on_worker_media_loaded)
        worker.end_reached.connect(self.end_reached)
        worker.error_occurred.connect(self.error_occurred)

        thread.started.connect(worker.initialize_and_play)
        
        self.active_worker = worker
        self.active_thread = thread
        self._current_media_path = media_path
        
        thread.start()
        
        QTimer.singleShot(100, lambda: self._apply_cached_settings())
        return True

    def _retire_active_worker(self):
        if not self.active_worker or not self.active_thread:
            return

        old_worker = self.active_worker
        old_thread = self.active_thread
        old_surface_id = getattr(old_worker, "surface_id", None)

        # Ask the old worker to stop in its own thread (queued)
        try:
            old_worker.sig_stop_command.emit()
        except Exception:
            # Fallback (should be rare)
            try:
                QMetaObject.invokeMethod(old_worker, "stop_and_cleanup", Qt.ConnectionType.QueuedConnection)
            except Exception:
                pass

        self.zombie_threads.append(old_thread)
        old_worker.sig_done.connect(old_thread.quit)
        old_thread.finished.connect(lambda: self._cleanup_zombie(old_thread))
        if old_surface_id:
            old_thread.finished.connect(lambda sid=old_surface_id: self.surface_released.emit(int(sid)))
        old_thread.finished.connect(old_thread.deleteLater)
        old_thread.finished.connect(old_worker.deleteLater)

        self.active_worker = None
        self.active_thread = None

    def _cleanup_zombie(self, thread):
        if thread in self.zombie_threads:
            self.zombie_threads.remove(thread)
            Logger.instance().debug(caller="VLCBackend", msg=f"Zombie thread cleaned up. Remaining: {len(self.zombie_threads)}")

    def _apply_cached_settings(self):
        if self._current_volume != 100:
            self._sig_worker_set_vol.emit(self._current_volume)
        if self._current_rate != 1.0:
            self._sig_worker_set_rate.emit(self._current_rate)

    def _on_worker_state_changed(self, state):
        if state == "playing": self._is_playing = True
        elif state in ["paused", "stopped"]: self._is_playing = False
        self.state_changed.emit(state)

    def _on_worker_position_changed(self, pos):
        self._current_position = pos
        self.position_changed.emit(pos)

    def _on_worker_duration_changed(self, dur):
        self._current_duration = dur
        self.duration_changed.emit(dur)
        
    def _on_worker_media_loaded(self, meta, is_video, audio_tracks, sub_tracks):
        self._cached_audio_tracks = audio_tracks
        self._cached_subtitle_tracks = sub_tracks
        
        # Artwork extraction fallback
        if not meta.get('artwork_path'):
             meta['artwork_path'] = self._extract_album_art(self._current_media_path)
             
        self.media_loaded.emit(meta, is_video)

    def _extract_album_art(self, file_path):
        """Extracts artwork using Mutagen (synchronous but rare)."""
        try:
            temp_dir = os.path.join(os.path.expanduser("~"), ".music_player_temp")
            os.makedirs(temp_dir, exist_ok=True)
            import hashlib
            file_hash = hashlib.md5(file_path.encode()).hexdigest()
            artwork_path = os.path.join(temp_dir, f"cover_{file_hash}.jpg")
            if os.path.exists(artwork_path): return artwork_path

            import mutagen
            from mutagen.id3 import ID3, APIC
            from mutagen.mp3 import MP3
            from mutagen.flac import FLAC
            
            if file_path.lower().endswith('.mp3'):
                audio = MP3(file_path)
                if audio.tags:
                    for tag in audio.tags.values():
                        if isinstance(tag, APIC) and tag.data:
                            with open(artwork_path, 'wb') as img:
                                img.write(tag.data)
                            return artwork_path
            elif file_path.lower().endswith('.flac'):
                audio = FLAC(file_path)
                if audio.pictures:
                    with open(artwork_path, 'wb') as img:
                        img.write(audio.pictures[0].data)
                    return artwork_path
        except Exception as e:
            Logger.instance().debug(caller="VLCBackend", msg=f"Artwork extract failed: {e}")
        return None

    # Public API
    def play(self):
        self._sig_worker_play.emit()
        return True 

    def pause(self):
        self._sig_worker_pause.emit()
        return True

    def stop(self):
        if self.active_worker:
            self._retire_active_worker()
        self.state_changed.emit("stopped")
        return True

    def seek(self, pos):
        self._sig_worker_seek.emit(pos)
        return True 

    def set_volume(self, vol):
        self._current_volume = vol
        self._sig_worker_set_vol.emit(vol)

    def set_rate(self, rate):
        self._current_rate = rate
        self._sig_worker_set_rate.emit(rate)
        
    def set_audio_track(self, track_id):
        self._sig_worker_set_audio.emit(track_id)
        return True
        
    def set_video_output(self, hwnd):
        self._hwnd = hwnd

    def get_current_position(self): return self._current_position
    def get_duration(self): return self._current_duration
    def get_volume(self): return self._current_volume
    def get_rate(self): return self._current_rate
    def is_playing(self): return self._is_playing
    def get_current_media_path(self): return self._current_media_path

    # Track Listings (Cached)
    def get_audio_tracks(self): return self._cached_audio_tracks
    def get_subtitle_tracks(self): return self._cached_subtitle_tracks
    def has_subtitle_tracks(self): return len(self._cached_subtitle_tracks) > 0
    def has_multiple_audio_tracks(self): return len(self._cached_audio_tracks) > 1
    
    def enable_subtitles(self, track_id): 
        self._sig_worker_set_spu.emit(track_id)
        return True
    def disable_subtitles(self):
        self._sig_worker_set_spu.emit(-1)
        return True

    def cleanup(self):
        if self.active_worker:
            self._retire_active_worker()
