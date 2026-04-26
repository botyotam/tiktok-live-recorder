import asyncio
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

            info = json.loads(stdout.decode())
            if info.get('is_live'):
                # yt-dlp should provide the direct stream URL if live
                # For TikTok, yt-dlp usually gives a direct HLS/DASH URL
                return info.get('url'), None
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
        command = [
            "ffmpeg",
            "-i", stream_url,
            "-c", "copy",
            "-map", "0",
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov", # Optimize for fragmented output
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
        # Monitor stderr for ffmpeg output to detect hangs or errors
        # This is a simplified monitoring. A more robust solution might parse stderr for progress.
        try:
            while process.returncode is None:
                line = await process.stderr.readline()
                if not line:
                    break # EOF
                # Update last_activity to prevent timeout if ffmpeg is still writing
                self.active_recordings[chat_id]['last_activity'] = time.time()
                # print(f"FFMPEG [{chat_id}]: {line.decode().strip()}") # For debugging

                # Check for timeout
                if time.time() - self.active_recordings[chat_id]['last_activity'] > FFMPEG_TIMEOUT:
                    print(f"FFmpeg process for {chat_id} timed out. Killing.")
                    process.terminate()
                    await process.wait()
                    self.active_recordings[chat_id]['status'] = 'timed_out'
                    break

                await asyncio.sleep(1) # Check every second

            await process.wait() # Ensure process is fully terminated
            if process.returncode != 0 and self.active_recordings[chat_id]['status'] != 'stopped':
                print(f"FFmpeg process for {chat_id} exited with error: {process.returncode}")
                self.active_recordings[chat_id]['status'] = 'error'
            elif self.active_recordings[chat_id]['status'] == 'recording':
                self.active_recordings[chat_id]['status'] = 'finished'

        except asyncio.CancelledError:
            print(f"Monitoring for {chat_id} cancelled.")
        except Exception as e:
            print(f"Error monitoring ffmpeg for {chat_id}: {e}")
            self.active_recordings[chat_id]['status'] = 'error'

    async def stop_recording(self, chat_id):
        if chat_id not in self.active_recordings or self.active_recordings[chat_id]['status'] != 'recording':
            return False, "No active recording to stop."

        record_info = self.active_recordings[chat_id]
        process = record_info['process']
        filename = record_info['filename']

        try:
            process.terminate() # Send SIGTERM to ffmpeg
            await process.wait() # Wait for it to terminate
            self.active_recordings[chat_id]['status'] = 'stopped'
            return True, f"Recording for @{record_info['username']} stopped. File: {os.path.basename(filename)}"
        except Exception as e:
            return False, f"Failed to stop ffmpeg: {e}"

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

        return (
            f"Status: {status.replace('_', ' ').title()}\n"
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

import json # Moved import json here to avoid circular dependency if config imports recorder
