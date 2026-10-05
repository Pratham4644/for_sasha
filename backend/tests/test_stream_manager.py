import pytest
from backend.app.services.stream_manager import StreamManager


def test_source_url_construction():
    sm = StreamManager()

    # Simple RTSP
    url = sm._build_source_url("rtsp://192.168.1.50:554/live")
    assert url == "rtsp://192.168.1.50:554/live"

    # With credentials
    url_creds = sm._build_source_url("rtsp://192.168.1.50:554/live", "admin", "p@ss:word")
    assert "admin:p%40ss%3Aword@192.168.1.50:554" in url_creds

    # HTTP without scheme
    url_http = sm._build_source_url("192.168.1.50:8080/video.mjpg")
    assert url_http == "http://192.168.1.50:8080/video.mjpg"


def test_ffmpeg_command_generation():
    sm = StreamManager()
    cmd = sm._get_ffmpeg_cmd(
        source_url="rtsp://192.168.1.10/stream",
        destination_url="rtsp://localhost:8554/test_cam",
        resolution="1280x720",
        fps=15.0,
    )
    assert "ffmpeg" in cmd[0]
    assert "-i" in cmd
    assert "rtsp://192.168.1.10/stream" in cmd
    assert "rtsp://localhost:8554/test_cam" in cmd
    assert "scale=1280:720" in cmd
    assert "-f" in cmd
    assert "rtsp" in cmd
    # FFmpeg 9.x RTSP demuxer uses -timeout (us), not legacy -stimeout
    assert "-stimeout" not in cmd
    assert "-timeout" in cmd
    assert "-rtsp_transport" in cmd
