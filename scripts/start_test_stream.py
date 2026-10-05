import os
import subprocess
import time
import sys

def main():
    print("=================================================================")
    print("  LOCAL TEST STREAM GENERATOR")
    print("=================================================================")
    print("Starting a simulated RTSP stream to MediaMTX at rtsp://localhost:8554/test-cam")
    
    cmd = [
        "ffmpeg",
        "-re",
        "-f", "lavfi",
        "-i", "testsrc=size=1280x720:rate=15",
        "-f", "lavfi",
        "-i", "sine=frequency=1000:sample_rate=44100",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-b:v", "500k",
        "-c:a", "aac",
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        "rtsp://localhost:8554/test-cam"
    ]
    
    print("Command:", " ".join(cmd))
    
    try:
        process = subprocess.Popen(cmd)
        print("\nTest stream is running! Keep this terminal open.")
        print("To test the stream locally in the platform:")
        print("1. Start the platform backend (run_all.bat)")
        print("2. Go to the Cameras page")
        print("3. Click 'Add Camera'")
        print("4. Set Source URL to: rtsp://localhost:8554/test-cam")
        print("5. Save and view the stream in the UI.")
        print("\nPress Ctrl+C to stop the test stream.")
        
        while True:
            time.sleep(1)
            if process.poll() is not None:
                print("\nFFmpeg exited unexpectedly. Is MediaMTX running?")
                break
                
    except KeyboardInterrupt:
        print("\nStopping test stream...")
        process.terminate()
        process.wait()
        print("Test stream stopped.")
    except Exception as e:
        print(f"Failed to start FFmpeg: {e}")

if __name__ == "__main__":
    main()
