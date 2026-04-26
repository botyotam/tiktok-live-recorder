import asyncio
import os
import re
import time
from datetime import datetime

from config import FFMPEG_TIMEOUT, RECORDINGS_DIR

class TikTokRecorder:
    def __init__(self):
        self.active_recordings = {}
        os.makedirs(RECORDINGS_DIR, exist_ok=True)

    async def _get_tiktok_username(self, identifier):
        match = re.search(r"tiktok.com/@([a-zA-Z0-9._-]+)", identifier)
        if match:
            return match.group(1)
        return identifier.lstrip('@')

    async def start_recording(self, chat_id, identifier):
        username = await self._get_tiktok_username(identifier)
        if not username:
            return False, "Invalid TikTok username or URL."

        if chat_id in self.active_recordings and self.active_recordings[chat_id]['status'] == 'recording':
            return False, f"Already recording for {self.active_recordings[chat_id]['username']}."

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(RECORDINGS_DIR, f"tiktok_{username}_{timestamp}.mp4")
        
        # Simple and lightweight command using yt-dlp's native capability
        # This avoids the complex ffmpeg pipe and uses yt-dlp's own downloader which is more stable for TikTok
        command = [
            "yt-dlp",
            "--quiet", "--no-warnings",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "--output", filename,
            f"https://www.tiktok.com/@{username}/live"
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
            
            # Start monitoring in background
            asyncio.create_task(self._monitor_process(chat_id, process, filename))
            
            return True, f"Recording started for @{username}. Please wait a few seconds for the file to be created."
        except Exception as e:
            return False, f"Failed to start recording: {e}"

    async def _monitor_process(self, chat_id, process, filename):
        last_file_size = 0
        last_size_check_time = time.time()
        
        try:
            while process.returncode is None:
                await asyncio.sleep(10) # Check every 10 seconds
                
                if os.path.exists(filename):
                    current_size = os.path.getsize(filename)
                    if current_size > last_file_size:
                        last_file_size = current_size
                        last_size_check_time = time.time()
                    elif time.time() - last_size_check_time > FFMPEG_TIMEOUT:
                        print(f"Recording for {chat_id} timed out.")
                        process.terminate()
                        self.active_recordings[chat_id]['status'] = 'timed_out'
                        break
                elif time.time() - last_size_check_time > 60: # If file not created after 60s
                    print(f"File not created for {chat_id}. Terminating.")
                    process.terminate()
                    self.active_recordings[chat_id]['status'] = 'error'
                    self.active_recordings[chat_id]['error_msg'] = "File not created (User might not be live)"
                    break

            stdout, stderr = await process.communicate()
            if process.returncode != 0 and self.active_recordings[chat_id]['status'] == 'recording':
                error_msg = stderr.decode().strip()
                if "is not live" in error_msg.lower():
                    self.active_recordings[chat_id]['status'] = 'error'
                    self.active_recordings[chat_id]['error_msg'] = "User is not live."
                else:
                    self.active_recordings[chat_id]['status'] = 'error'
                    self.active_recordings[chat_id]['error_msg'] = error_msg or f"Exit code {process.returncode}"
            elif self.active_recordings[chat_id]['status'] == 'recording':
                self.active_recordings[chat_id]['status'] = 'finished'
                
        except Exception as e:
            print(f"Monitor error for {chat_id}: {e}")
            if chat_id in self.active_recordings:
                self.active_recordings[chat_id]['status'] = 'error'
                self.active_recordings[chat_id]['error_msg'] = str(e)

    async def stop_recording(self, chat_id):
        if chat_id not in self.active_recordings:
            return False, "No active recording."
        
        record_info = self.active_recordings[chat_id]
        if record_info['status'] == 'recording':
            try:
                record_info['process'].terminate()
                await record_info['process'].wait()
                record_info['status'] = 'stopped'
                return True, f"Stopped recording for @{record_info['username']}."
            except Exception as e:
                return False, f"Error stopping: {e}"
        else:
            username = record_info['username']
            self.clear_recording_info(chat_id)
            return True, f"Cleared status for @{username}."

    async def get_recording_status(self, chat_id):
        if chat_id not in self.active_recordings:
            return "No active recording."

        info = self.active_recordings[chat_id]
        duration = int(time.time() - info['start_time'])
        size = os.path.getsize(info['filename']) if os.path.exists(info['filename']) else 0
        
        status = info['status'].replace('_', ' ').title()
        msg = f"Status: {status}\nUsername: @{info['username']}\nDuration: {duration // 60}m {duration % 60}s\nSize: {size / (1024*1024):.2f} MB"
        if 'error_msg' in info:
            msg += f"\nError: {info['error_msg']}"
        return msg

    def get_recording_file(self, chat_id):
        return self.active_recordings.get(chat_id, {}).get('filename')

    def clear_recording_info(self, chat_id):
        if chat_id in self.active_recordings:
            del self.active_recordings[chat_id]

    def delete_recording_file(self, filename):
        if os.path.exists(filename):
            os.remove(filename)
            return True
        return False
