import subprocess

def get_video_duration(file_path):
    """Extract video duration using ffprobe"""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'quiet', 
            '-show_entries', 'format=duration', 
            '-of', 'csv=p=0', 
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        return int(duration)  # Return duration in seconds as integer
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        # Return None if ffprobe is not available or fails
        return None