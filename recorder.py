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
        
        # Using yt-dlp with specific flags for better stability and error reporting
        # --part: Use .part files to see progress
        # --no-part: Actually, for real-time monitoring, we might prefer direct writing or knowing where the part is.
        # yt-dlp by default uses .part.
        command = [
            "yt-dlp",
            "--no-warnings",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--output", filename,
            "--hls-prefer-ffmpeg", # Use ffmpeg for HLS which is often more robust for live streams
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
                'last_activity': time.time(),
                'error_detail': None
            }
            
            # Start monitoring in background
            asyncio.create_task(self._monitor_process(chat_id, process, filename))
            
            return True, f"Recording started for @{username}. Use /status to check progress."
        except Exception as e:
            return False, f"Failed to start recording: {e}"

    async def _monitor_process(self, chat_id, process, filename):
        last_file_size = 0
        last_size_check_time = time.time()
        part_filename = filename + ".part"
        
        try:
            # We also want to capture stderr to provide better error messages
            stderr_buffer = []

            async def read_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    decoded_line = line.decode().strip()
                    if decoded_line:
                        stderr_buffer.append(decoded_line)
                        if len(stderr_buffer) > 20: # Keep last 20 lines
                            stderr_buffer.pop(0)

            stderr_task = asyncio.create_task(read_stderr())

            while process.returncode is None:
                await asyncio.sleep(10) # Check every 10 seconds
                
                # Check both filename and part_filename
                current_file = None
                if os.path.exists(filename):
                    current_file = filename
                elif os.path.exists(part_filename):
                    current_file = part_filename
                
                if current_file:
                    current_size = os.path.getsize(current_file)
                    if current_size > last_file_size:
                        last_file_size = current_size
                        last_size_check_time = time.time()
                    elif time.time() - last_size_check_time > FFMPEG_TIMEOUT:
                        print(f"Recording for {chat_id} timed out due to inactivity.")
                        process.terminate()
                        self.active_recordings[chat_id]['status'] = 'error'
                        self.active_recordings[chat_id]['error_detail'] = "Inactivity timeout (Stream might have ended)"
                        break
                elif time.time() - last_size_check_time > 60: # If file not created after 60s
                    print(f"File not created for {chat_id} after 60s.")
                    process.terminate()
                    self.active_recordings[chat_id]['status'] = 'error'
                    self.active_recordings[chat_id]['error_detail'] = "File not created (User might not be live or connection failed)"
                    break

            # Wait for process to finish
            return_code = await process.wait()
            await stderr_task

            if chat_id in self.active_recordings:
                info = self.active_recordings[chat_id]
                
                # If it was still "recording" but finished, check if it was successful
                if info['status'] == 'recording':
                    if return_code == 0:
                        info['status'] = 'finished'
                    else:
                        info['status'] = 'error'
                        # Use the last few lines of stderr as detail if not already set
                        if not info['error_detail']:
                            info['error_detail'] = "\n".join(stderr_buffer[-3:]) if stderr_buffer else f"Exit code {return_code}"
                
                # Handle case where yt-dlp finishes but leaves .part file
                if os.path.exists(part_filename) and not os.path.exists(filename):
                    os.rename(part_filename, filename)
                    
        except Exception as e:
            print(f"Monitor error for {chat_id}: {e}")
            if chat_id in self.active_recordings:
                self.active_recordings[chat_id]['status'] = 'error'
                self.active_recordings[chat_id]['error_detail'] = str(e)

    async def stop_recording(self, chat_id):
        if chat_id not in self.active_recordings:
            return False, "No active recording."
        
        record_info = self.active_recordings[chat_id]
        if record_info['status'] == 'recording':
            try:
                record_info['process'].terminate()
                await record_info['process'].wait()
                record_info['status'] = 'stopped'
                
                # Final check for .part file
                part_filename = record_info['filename'] + ".part"
                if os.path.exists(part_filename) and not os.path.exists(record_info['filename']):
                    os.rename(part_filename, record_info['filename'])
                
                return True, f"Stopped recording for @{record_info['username']}."
            except Exception as e:
                return False, f"Error stopping: {e}"
        else:
            username = record_info['username']
            # If already in error/finished state, just clear it
            self.clear_recording_info(chat_id)
            return True, f"Cleared status for @{username}."

    async def get_recording_status(self, chat_id):
        if chat_id not in self.active_recordings:
            return "No active recording."

        info = self.active_recordings[chat_id]
        duration = int(time.time() - info['start_time'])
        
        # Check size of either .mp4 or .mp4.part
        filename = info['filename']
        part_filename = filename + ".part"
        size = 0
        if os.path.exists(filename):
            size = os.path.getsize(filename)
        elif os.path.exists(part_filename):
            size = os.path.getsize(part_filename)
        
        status_text = info['status'].replace('_', ' ').title()
        msg = f"Status: {status_text}\n"
        msg += f"Username: @{info['username']}\n"
        msg += f"Duration: {duration // 3600:02d}:{(duration % 3600) // 60:02d}:{duration % 60:02d}\n"
        msg += f"File Size: {size / (1024*1024):.2f} MB"
        
        if info.get('error_detail'):
            msg += f"\nError Detail: {info['error_detail']}"
        
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
        # Also check for .part
        if os.path.exists(filename + ".part"):
            os.remove(filename + ".part")
            return True
        return False
