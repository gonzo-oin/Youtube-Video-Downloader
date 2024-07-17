from flask import Blueprint, redirect, render_template, request, flash, send_file, url_for, session
from flask_login import login_required, current_user
from .models import Video
from . import db

# from pytube import YouTube, Playlist, Stream
from youtubesearchpython import VideosSearch, PlaylistsSearch
from moviepy.editor import AudioFileClip
import mutagen

from pytubefix import YouTube, Stream
from pytubefix.cli import on_progress

from io import BytesIO
from shutil import rmtree
import os
import zipfile

views = Blueprint("views", __name__)

## Pages

@views.route("/")
def home():
    # Clears the session data and redirects to video conversion page: "/video"
    session.clear()
    return redirect(url_for("views.video"))

@views.route("/video", methods=["GET", "POST"])
def video():
    # Check if post request
    if request.method == "GET":
        url = request.headers.get("url")
        #url = request.form.get("url")
        #date = request.form.get("date")
        
        session.clear()

        # Try converting a url to a downloadable video
        try:
            yt = YouTube(url)
        except Exception:
            if "playlist?" in url:
                flash("Playlists can only be converted on the playlist page.", category="error")
            else:
                flash("Video URL is not valid.", category="error")
            return render_template("video.html", user=current_user)
        
        # Assign the file type and donwloads path
        file_type = "mp4" # if request.form["convert"] == "mp4" else "mp3"
        downloads_path = os.path.join(os.getcwd(), "temp")

        videobis = yt.streams.get_highest_resolution()
        return redirect(videobis.url)
# Try downloading the converted video
        try:
            video = download_video(yt, file_type, downloads_path, True)
        except Exception:
            flash("Video could not be downloaded.", category="error")
            return render_template("video.html", user=current_user)

        file_path = os.path.join(downloads_path, video.default_filename)

        # Convert to mp3
        try:
            if file_type == "mp3":
                file_path_mp3 = file_path.replace("mp4", "mp3")
                if os.path.exists(file_path_mp3):
                    os.remove(file_path_mp3)
                
                file_path = convert_to_mp3_with_metadata(file_path)
        except Exception:
            flash("Video could not be converted to an MP3 format successfully. File cannot be found or already exists.", category="error")
            return render_template("video.html", user=current_user)

        # Update file metadata
        update_metadata(file_path, yt.title, yt.author)

        # Save conversion to user history
        #save_history(url, date, video.title, "video", file_type)
        
        # Try sending the file to the browser to be downloaded
        try:
            downloaded_file = send_file(path_or_file=file_path, as_attachment=True)
            rmtree(downloads_path)
            return downloaded_file
        except Exception:
           flash("Video converted successfully, but the file couldn't be sent to the browser! Saved to temporary folder.", category="warning")
           print(f"File stored at: {file_path}")

    # Clear playlist url session data and try to retrieve video url session data
    session["playlist_url"] = ""
    try: url = session["video_url"]
    except Exception: url = ""

    return render_template("video.html", user=current_user, url=url)

## Functions

def convert_to_mp3_with_metadata(file_path: str) -> str:
    # Use moviepy to convert an mp4 to an mp3 with metadata support. Delete mp4 afterwards
    audio_clip = AudioFileClip(file_path)
    file_path = file_path.replace("mp4", "mp3")
    audio_clip.write_audiofile(file_path)
    audio_clip.close()
    os.remove(file_path.replace("mp3", "mp4"))
    return file_path

def update_metadata(file_path: str, title: str, artist: str, album: str="") -> None:
    # Update the file metadata according to YouTube video details
    with open(file_path, 'r+b') as file:
        media_file = mutagen.File(file, easy=True)
        media_file["title"] = title
        if album: media_file["album"] = album
        media_file["artist"] = artist
        media_file.save(file)

def convert_video_redirect(form_name: str) -> str:
    # Save video url in session data and redirect to corresponding page
    conversion_info = request.form.get(form_name)
    url, r_type = conversion_info.split()[0], conversion_info.split()[1]
    if r_type == "video":
        session["video_url"] = url
        redirect_page = "views.video"
    else:
        session["playlist_url"] = url
        redirect_page = "views.playlist"
    return redirect_page

def zip_folder(name: str, path: str) -> tuple[str, BytesIO]:
    # Zip a folder
    zip_file_name = f"{name}.zip"
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(path):
            for file in files:
                zipf.write(os.path.join(root, file))
            
    memory_file.seek(0)
    return zip_file_name, memory_file

def download_video(yt: YouTube, file_type: str, downloads_path: str, debug: bool=False) -> Stream:
    # Download a video and debug progress
    if file_type == "mp4":
        video = yt.streams.get_highest_resolution()
    else:
        video = yt.streams.filter(only_audio=True).get_audio_only()

    if debug:
        debug_video_progress(yt, video, file_type)

    video.download(downloads_path)
    return video

def save_history(url: str, date: str, title: str, link_type: str, file_type: str) -> None:
    # Save user history data in the generated database
    if current_user.is_authenticated:
        new_video = Video(title=title, url=url, date=date, link_type=link_type, file_type=file_type, user_id=current_user.id)
        db.session.add(new_video)
        db.session.commit()

## Debug functions

def debug_video_progress(yt: YouTube, video, file_type: str, extra_info: str=""):
    highest_res = f", Highest Resolution: {video.resolution}" if file_type == "mp4" else ""
    print(f"Fetching {extra_info}\"{video.title}\"")
    print(f"[File size: {round(video.filesize * 0.000001, 2)} MB{highest_res}, Author: {yt.author}]\n")