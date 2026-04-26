import asyncio
import os
import re
import time
import logging
from datetime import datetime

from config import FFMPEG_TIMEOUT, RECORDINGS_DIR

logger = logging.getLogger(__name__)

class TikTokRecorder:
    def __init__(self):
        self.active_recordings = {}
        os.makedirs(RECORDINGS_DIR, exist_ok=True)

    async def _get_tiktok_username(self, identifier):
        match = re.search(r"tiktok.com/@([a-zA-Z0-9._-]+)", identifier)
        if match:
            return match.group(1)
        return identifier.lstrip('@')

    async def is_live(self, username):
        """Check if a user is live before starting the actual recording."""
        command = [
            "yt-dlp",
            "--quiet", "--no-warnings",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--cookies-from-browser", "chrome",
            "--simulate", # Don't download
            f"https://www.tiktok.com/@{username}/live"
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Error checking live status for {username}: {e}")
            return False

    async def start_recording(self, chat_id, identifier):
        username = await self._get_tiktok_username(identifier)
        if not username:
            return False, "❌ Username atau URL TikTok tidak valid."

        if chat_id in self.active_recordings and self.active_recordings[chat_id]['status'] == 'recording':
            return False, f"⚠️ Sudah ada rekaman aktif untuk @{self.active_recordings[chat_id]['username']}."

        # Step 1: Check if live
        live_status = await self.is_live(username)
        if not live_status:
            return False, f"❌ @{username} saat ini tidak sedang Live."

        # Step 2: Start recording
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(RECORDINGS_DIR, f"tiktok_{username}_{timestamp}.mp4")
        
        command = [
            "yt-dlp",
            "--no-warnings",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--cookies-from-browser", "chrome",
            "--output", filename,
            "--hls-prefer-ffmpeg",
            "--hls-use-mpegts",
            "--no-check-certificates",
            "--concurrent-fragments", "5",
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
            
            return True, f"✅ Rekaman dimulai untuk @{username}!\nGunakan /status untuk melihat progres."
        except Exception as e:
            return False, f"❌ Gagal memulai rekaman: {e}"

    async def _monitor_process(self, chat_id, process, filename):
        last_file_size = 0
        last_size_check_time = time.time()
        part_filename = filename + ".part"
        
        try:
            stderr_buffer = []

            async def read_stderr():
                try:
                    while True:
                        line = await process.stderr.readline()
                        if not line:
                            break
                        decoded_line = line.decode().strip()
                        if decoded_line:
                            stderr_buffer.append(decoded_line)
                            if len(stderr_buffer) > 20:
                                stderr_buffer.pop(0)
                except Exception as e:
                    logger.error(f"Error reading stderr for {chat_id}: {e}")

            stderr_task = asyncio.create_task(read_stderr())

            while process.returncode is None:
                await asyncio.sleep(10)
                
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
                        logger.warning(f"Recording for {chat_id} timed out due to inactivity.")
                        try:
                            process.terminate()
                        except:
                            pass
                        if chat_id in self.active_recordings:
                            self.active_recordings[chat_id]['status'] = 'error'
                            self.active_recordings[chat_id]['error_detail'] = "Timeout (Stream mungkin sudah berakhir)"
                        break
                elif time.time() - last_size_check_time > 60:
                    logger.warning(f"File not created for {chat_id} after 60s.")
                    try:
                        process.terminate()
                    except:
                        pass
                    if chat_id in self.active_recordings:
                        self.active_recordings[chat_id]['status'] = 'error'
                        self.active_recordings[chat_id]['error_detail'] = "File tidak terbuat (User mungkin tidak Live)"
                    break

            return_code = await process.wait()
            stderr_task.cancel()

            if chat_id in self.active_recordings:
                info = self.active_recordings[chat_id]
                if info['status'] == 'recording':
                    if return_code == 0:
                        info['status'] = 'finished'
                    else:
                        info['status'] = 'error'
                        if not info['error_detail']:
                            error_text = "\n".join(stderr_buffer)
                            if "404 Not Found" in error_text:
                                info['error_detail'] = "URL Stream kedaluwarsa (404). TikTok memblokir atau stream berakhir."
                            elif "is not live" in error_text.lower():
                                info['error_detail'] = "User tidak sedang Live."
                            else:
                                info['error_detail'] = "\n".join(stderr_buffer[-3:]) if stderr_buffer else f"Exit code {return_code}"
                
                if os.path.exists(part_filename) and not os.path.exists(filename):
                    try:
                        os.rename(part_filename, filename)
                    except Exception as e:
                        logger.error(f"Failed to rename part file for {chat_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Monitor error for {chat_id}: {e}")
            if chat_id in self.active_recordings:
                self.active_recordings[chat_id]['status'] = 'error'
                self.active_recordings[chat_id]['error_detail'] = str(e)

    async def stop_recording(self, chat_id):
        if chat_id not in self.active_recordings:
            return False, "❌ Tidak ada rekaman aktif."
        
        record_info = self.active_recordings[chat_id]
        if record_info['status'] == 'recording':
            try:
                process = record_info['process']
                logger.info(f"Terminating process for {chat_id}...")
                process.terminate()
                
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                    logger.info(f"Process for {chat_id} terminated gracefully.")
                except asyncio.TimeoutError:
                    logger.warning(f"Process for {chat_id} did not terminate, killing...")
                    process.kill()
                    await process.wait()
                
                record_info['status'] = 'stopped'
                
                filename = record_info['filename']
                part_filename = filename + ".part"
                if os.path.exists(part_filename) and not os.path.exists(filename):
                    try:
                        os.rename(part_filename, filename)
                    except:
                        pass
                
                return True, f"✅ Rekaman untuk @{record_info['username']} telah dihentikan."
            except Exception as e:
                logger.error(f"Error stopping recording for {chat_id}: {e}")
                return False, f"❌ Gagal menghentikan: {e}"
        else:
            username = record_info['username']
            self.clear_recording_info(chat_id)
            return True, f"✅ Status untuk @{username} telah dibersihkan."

    async def get_recording_status(self, chat_id):
        if chat_id not in self.active_recordings:
            return "❌ Tidak ada rekaman aktif."

        info = self.active_recordings[chat_id]
        duration = int(time.time() - info['start_time'])
        
        filename = info['filename']
        part_filename = filename + ".part"
        size = 0
        if os.path.exists(filename):
            size = os.path.getsize(filename)
        elif os.path.exists(part_filename):
            size = os.path.getsize(part_filename)
        
        status_text = info['status'].replace('_', ' ').title()
        msg = f"📊 **Status Perekaman**\n\n"
        msg += f"👤 Username: @{info['username']}\n"
        msg += f"⏳ Status: {status_text}\n"
        msg += f"⏱ Durasi: {duration // 3600:02d}:{(duration % 3600) // 60:02d}:{duration % 60:02d}\n"
        msg += f"📦 Ukuran File: {size / (1024*1024):.2f} MB"
        
        if info.get('error_detail'):
            msg += f"\n\n❌ **Detail Error:**\n{info['error_detail']}"
        
        return msg

    def get_recording_file(self, chat_id):
        return self.active_recordings.get(chat_id, {}).get('filename')

    def clear_recording_info(self, chat_id):
        if chat_id in self.active_recordings:
            del self.active_recordings[chat_id]

    def delete_recording_file(self, filename):
        try:
            if os.path.exists(filename):
                os.remove(filename)
                return True
            if os.path.exists(filename + ".part"):
                os.remove(filename + ".part")
                return True
        except Exception as e:
            logger.error(f"Error deleting file {filename}: {e}")
        return False
