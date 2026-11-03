from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from src.config import get_resource_path, settings
from src.core.tts_service import tts_service


class AudioManager(QObject):
    """Bộ phát âm thanh nền (Ambient Rain), tiếng chuông nhắc nhở (Mindful Chime), và TTS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tts = tts_service
        self.ambient_player = QMediaPlayer(self)
        self.ambient_output = QAudioOutput(self)
        self.ambient_output.setVolume(0.35)
        self.ambient_player.setAudioOutput(self.ambient_output)

        rain_path = get_resource_path("assets/sounds/rain.wav")
        if rain_path.exists():
            self.ambient_player.setSource(QUrl.fromLocalFile(str(rain_path)))
            self.ambient_player.setLoops(QMediaPlayer.Loops.Infinite)

        self.chime_player = QMediaPlayer(self)
        self.chime_output = QAudioOutput(self)
        self.chime_output.setVolume(0.65)
        self.chime_player.setAudioOutput(self.chime_output)

        chime_path = get_resource_path("assets/sounds/chime.wav")
        if chime_path.exists():
            self.chime_player.setSource(QUrl.fromLocalFile(str(chime_path)))

    def play_chime(self):
        try:
            self.chime_player.stop()
            self.chime_player.play()
        except Exception:
            pass

    def toggle_ambient(self, enable: bool | None = None) -> bool:
        if enable is None:
            enable = self.ambient_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        try:
            if enable:
                self.ambient_player.play()
            else:
                self.ambient_player.pause()
        except Exception:
            pass
        settings.ambient_sound_enabled = enable
        settings.save()
        return enable

    @property
    def is_ambient_playing(self) -> bool:
        return self.ambient_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
