import asyncio
import json
import os
import re
import subprocess
import time
from datetime import datetime

from config import FFMPEG_TIMEOUT, RECORDINGS_DIR

class TikTokRecorder:
    def __init__(self):
        self.active_recordings = {}
        os.makedirs(RECORDINGS_DIR, exist_ok=True)

    async def _get_tiktok_username(self, identifier):
        # Extract username from URL if provided
        match = re.search(r"tiktok.com/@([a-zA-Z0-9._-]+)", identifier)
        if match:
            return match.group(1)
        # Remove @ if present
        return identifier.lstrip('@')

    async def _get_live_stream_url(self, username):
        try:
            # Use yt-dlp to extract info, specifically looking for live status and stream URL
            process = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "--dump-json",
                f"https://www.tiktok.com/@{username}/live",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                print(f"yt-dlp error for {username}: {stderr.decode()}")
                if "is not live" in stderr.decode().lower():
                    return None, "User is not live."
                return None, f"Failed to get stream info: {stderr.decode()}"

            # json is already imported at the top of the file
            info = json.loads(stdout.decode())
            if info.get('is_live'):
                stream_url = None
                # Prioritize direct URL if it's a good candidate (e.g., HLS/DASH)
                if info.get("url") and ("m3u8" in info["url"] or "mpd" in info["url"]):
                    stream_url = info["url"]
                    print(f"DEBUG: yt-dlp direct URL (HLS/DASH) found: {stream_url}")
                
                # If not found, iterate through formats
                if not stream_url and info.get("formats"):
                    # Try to find HLS or DASH formats first
                    for f in info["formats"]:
                        if f.get("url") and f.get("protocol") in ["hls", "dash"]:
                            stream_url = f["url"]
                            print(f"DEBUG: yt-dlp format (HLS/DASH) found: {stream_url}")
                            break
                    # If still not found, try any https format
                    if not stream_url:
                        for f in info["formats"]:
                            if f.get("url") and f.get("protocol") == "https":
                                stream_url = f["url"]
                                print(f"DEBUG: yt-dlp format (HTTPS) found: {stream_url}")
                                break
                
                if stream_url:
                    return stream_url, None
                else:
                    print(f"DEBUG: No suitable stream URL found in yt-dlp output for {username}. Full info: {info}")
                    return None, "Could not find a suitable live stream URL."
            else:
                return None, "User is not live."
        except Exception as e:
            return None, f"Error extracting stream URL: {e}"

    async def start_recording(self, chat_id, identifier):
        username = await self._get_tiktok_username(identifier)
        if not username:
            return False, "Invalid TikTok username or URL."

        if chat_id in self.active_recordings and self.active_recordings[chat_id]['status'] == 'recording':
            return False, f"Already recording for {self.active_recordings[chat_id]['username']}. Please stop current recording first."

        stream_url, error = await self._get_live_stream_url(username)
        if error:
            return False, error
        if not stream_url:
            return False, "Could not find live stream URL."

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(RECORDINGS_DIR, f"tiktok_{username}_{timestamp}.mp4")

        # ffmpeg command to record without re-encoding (codec copy)
        # Added -reconnect flags for better stream stability
        command = [
            "ffmpeg",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-i", stream_url,
            "-c", "copy",
            "-map", "0",
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov", # Optimize for fragmented output
            "-y", # Overwrite output files without asking
            filename
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self.active_recordings[chat_id] = {
                'username': username,
                'filename': filename,
                'process': process,
                'start_time': time.time(),
                'status': 'recording',
                'last_activity': time.time()
            }
            asyncio.create_task(self._monitor_ffmpeg_process(chat_id, process, filename))
            return True, f"Recording started for @{username}. File: {os.path.basename(filename)}"
        except Exception as e:
            return False, f"Failed to start ffmpeg: {e}"

    async def _monitor_ffmpeg_process(self, chat_id, process, filename):
        last_file_size = 0
        last_size_check_time = time.time()
        error_log = []
        try:
            # Read stderr in the background to capture errors
            async def read_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    decoded_line = line.decode().strip()
                    if "error" in decoded_line.lower() or "failed" in decoded_line.lower():
                        error_log.append(decoded_line)
                    # Keep only last 10 error lines
                    if len(error_log) > 10:
                        error_log.pop(0)

            stderr_task = asyncio.create_task(read_stderr())

            while process.returncode is None:
                await asyncio.sleep(5)  # Check every 5 seconds

                if not os.path.exists(filename):
                    # Check if process is still alive
                    if process.returncode is None:
                        print(f"FFmpeg process for {chat_id}: Recording file {filename} not found. Terminating.")
                        process.terminate()
                        await process.wait()
                        self.active_recordings[chat_id]['status'] = 'error'
                        self.active_recordings[chat_id]['error_msg'] = "File not created"
                    break

                current_file_size = os.path.getsize(filename)
                if current_file_size == last_file_size:
                    if time.time() - last_size_check_time > FFMPEG_TIMEOUT:
                        print(f"FFmpeg process for {chat_id} timed out (no file size increase). Killing.")
                        process.terminate()
                        await process.wait()
                        self.active_recordings[chat_id]['status'] = 'timed_out'
                        break
                else:
                    last_file_size = current_file_size
                    last_size_check_time = time.time()

            await process.wait()
            stderr_task.cancel()
            
            if process.returncode != 0 and self.active_recordings[chat_id]['status'] not in ['stopped', 'timed_out']:
                print(f"FFmpeg process for {chat_id} exited with error: {process.returncode}")
                self.active_recordings[chat_id]['status'] = 'error'
                self.active_recordings[chat_id]['error_msg'] = "\n".join(error_log) if error_log else f"Exit code {process.returncode}"
            elif self.active_recordings[chat_id]['status'] == 'recording':
                self.active_recordings[chat_id]['status'] = 'finished'

        except asyncio.CancelledError:
            if process.returncode is None:
                process.terminate()
                await process.wait()
            if chat_id in self.active_recordings:
                self.active_recordings[chat_id]['status'] = 'stopped'
        except Exception as e:
            print(f"Error monitoring ffmpeg for {chat_id}: {e}")
            if chat_id in self.active_recordings:
                self.active_recordings[chat_id]['status'] = 'error'
                self.active_recordings[chat_id]['error_msg'] = str(e)
            if process.returncode is None:
                process.terminate()
                await process.wait()

    async def stop_recording(self, chat_id):
        if chat_id not in self.active_recordings:
            return False, "No active recording to stop."
        
        # If it's already in an error or finished state, just clear it
        if self.active_recordings[chat_id]['status'] in ['stopped', 'finished', 'error', 'timed_out']:
            username = self.active_recordings[chat_id]['username']
            filename = self.active_recordings[chat_id]['filename']
            self.clear_recording_info(chat_id)
            return True, f"Cleared inactive recording for @{username}. File: {os.path.basename(filename)}"

        record_info = self.active_recordings[chat_id]
        process = record_info['process']
        filename = record_info['filename']

        try:
            if process.returncode is None:
                process.terminate()  # Send SIGTERM to ffmpeg
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    print(f"FFmpeg process for {chat_id} did not terminate gracefully. Killing.")
                    process.kill()
                    await process.wait()
            
            self.active_recordings[chat_id]['status'] = 'stopped'
            return True, f"Recording for @{record_info['username']} stopped. File: {os.path.basename(filename)}"
        except Exception as e:
            print(f"Error stopping ffmpeg for {chat_id}: {e}")
            return False, f"Failed to stop ffmpeg: {e}"
        finally:
            self.clear_recording_info(chat_id)

    async def get_recording_status(self, chat_id):
        if chat_id not in self.active_recordings:
            return "No active recording."

        record_info = self.active_recordings[chat_id]
        username = record_info['username']
        filename = record_info['filename']
        status = record_info['status']
        start_time = record_info['start_time']

        duration = int(time.time() - start_time)
        file_size = os.path.getsize(filename) if os.path.exists(filename) else 0

        status_text = f"Status: {status.replace('_', ' ').title()}\n"
        if status == 'error' and 'error_msg' in record_info:
            status_text += f"Error Detail: {record_info['error_msg']}\n"
            
        return (
            status_text +
            f"Username: @{username}\n"
            f"Duration: {duration // 3600:02d}:{(duration % 3600) // 60:02d}:{duration % 60:02d}\n"
            f"File Size: {file_size / (1024 * 1024):.2f} MB\n"
            f"File: {os.path.basename(filename)}"
        )

    def get_recording_file(self, chat_id):
        if chat_id in self.active_recordings and 'filename' in self.active_recordings[chat_id]:
            return self.active_recordings[chat_id]['filename']
        return None

    def clear_recording_info(self, chat_id):
        if chat_id in self.active_recordings:
            del self.active_recordings[chat_id]

    def delete_recording_file(self, filename):
        if os.path.exists(filename):
            os.remove(filename)
            return True
        return False


