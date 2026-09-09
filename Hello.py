import streamlit as st
from streamlit.logger import get_logger
import os, sys, requests, json
from os import walk
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo  # built-in module for time zones (Python 3.9+) thay cho from pytz import timezone
from Crypto.Cipher import AES
import base64
import psutil
import imageio_ffmpeg



LOGGER = get_logger(__name__)

def encrypt_payload_by_pycryptodome_place_clientside(key, payload_dict):
	plaintext = json.dumps(payload_dict).encode()
	cipher = AES.new(key, AES.MODE_EAX)
	ciphertext, tag = cipher.encrypt_and_digest(plaintext)
	encrypted = base64.urlsafe_b64encode(cipher.nonce + ciphertext).decode()
	return encrypted

def decrypt_payload_by_pycryptodome_place_serverside(key, encrypted_text):
	raw = base64.urlsafe_b64decode(encrypted_text.encode())
	nonce = raw[:16] # nonce = 16 bytes đầu
	ciphertext = raw[16:] # phần còn lại là ciphertext
	cipher = AES.new(key, AES.MODE_EAX, nonce=nonce)
	plaintext = cipher.decrypt(ciphertext)
	return json.loads(plaintext.decode())

def delete_files_in_temp_folder(defaultFolder='/tmp', Filename_extension='jpg'):
	#Get list of files im temp folder, then Delete all temp files
	import glob
	#st.write(glob.glob('/tmp/*.*'))                    
	#for f in glob.glob('/tmp/*.jpg'):    
	for f in glob.glob(f'{defaultFolder}/*.{Filename_extension}'):
		os.remove(f) 

# ========== START CỤM PCLOUD ==========
from pcloud import PyCloud
#PCLOUD_FOLDER_PATH = "/Temp-video"
# ---------- AUTHENTICATION ----------
def get_pcloud_client(email: str, password: str) -> PyCloud:
	try:
		pc = PyCloud(email, password)
		#st.write(pc) #show all token and methods
		st.success("Connected to pCloud successfully!")
		auth_token = pc.auth_token
		return pc, auth_token
	except Exception as e:
		st.error(f"Authentication failed: {e}")
		raise

# ---------- CREATE FOLDER ----------
def create_folder_pcloud(pc: PyCloud, folder_path: str) -> dict:
	try:
		res = pc.createfolder(path=folder_path)
		if res.get("result") == 0:
			st.info(f"Folder ready: {folder_path}")
		else:
			st.warning(f"Folder creation: {res}")
		return res
	except Exception as e:
		st.error(f"Error creating folder: {e}")
		return {}

# ---------- LISTING ALL FILES IN FOLDER ----------
def list_files_pcloud(pc: PyCloud, folderid: str):
	try:
		#json_data = pc.listfolder(path='/Temp-video')
		#json_data = pc.listfolder(folderid='27763883733')
		json_data = pc.listfolder(folderid=folderid)
		contents = json_data.get("metadata", {}).get("contents", [])
		if not contents:
			st.warning("No files found in folder.")
		else:
			st.success(f"Found {len(contents)} file(s) in {folderid}")
		return contents
	except Exception as e:
		st.error(f"Error listing files: {e}")
		return []

# ---------- DOWNLOAD ALL FILES IN A FOLDER ----------
def download_all_files_in_folder_pcloud(emailpcloud, passpcloud, folderidpcloud):
	pc, auth_token = get_pcloud_client(emailpcloud,passpcloud)
	#List all files in folder 
	result_json_data = list_files_pcloud(pc, folderidpcloud)
	#st.write(result_json_data) 
	video_path_arr = []
	for value in result_json_data:
		fileid = value["fileid"]
		fileName = value["name"]
		created = value["created"]
		st.write(f'fileid: {fileid} - fileName: {fileName} - created: {created}') 

		#Download fileid
		getlink_url = "https://api.pcloud.com/getfilelink"
		params = {
			"fileid": fileid,
			"auth": auth_token,
			'forcedownload': '1',
		}
		response = requests.get(getlink_url, params=params)
		host = response.json()["hosts"][0]
		path = response.json()["path"]
		direct_link_download = f'https://{host}{path}'
		#st.write(direct_link_download)
		response = requests.get(direct_link_download, params=params)
		file_bytes = response.content
		#st.video(file_bytes)
		filename_path = f'/tmp/{fileName}'
		with open(filename_path, 'wb') as f:
			f.write(file_bytes)
		video_path_arr.append(filename_path)
	return video_path_arr 

# ---------- FILE DOWNLOAD ----------
def download_file_pcloud(fileid: str, auth_token: str) -> bytes:
	try:
		res = requests.get(
			"https://api.pcloud.com/getfilelink",
			params={"fileid": fileid, "auth": auth_token, "forcedownload": "1"},
			timeout=10,
		)
		res.raise_for_status()
		data = res.json()
		host, path = data["hosts"][0], data["path"]
		direct_url = f"https://{host}{path}"
		file_response = requests.get(direct_url, timeout=15)
		file_response.raise_for_status()
		return file_response.content
	except Exception as e:
		st.error(f"Failed to download fileid {fileid}: {e}")
		return b""

# ---------- FILE UPLOAD ----------
def upload_files_pcloud(pc: PyCloud, files_Arr: list[str], folder_path: str):
	try:
		result = pc.uploadfile(files=files_Arr, path=folder_path)
		if result.get("result") == 0:
			st.success(f"Uploaded {len(files_Arr)} file(s) to {folder_path}")
		else:
			st.warning(f"Upload response: {result}")
		return result
	except Exception as e:
		st.error(f"Upload failed: {e}")
		return {}
# ========== END CỤM PCLOUD ==========

def send_email_by_resend(RESEND_API_KEY, email_receiver, subject, html_body):    
	current_date = str(datetime.now(ZoneInfo('Asia/Bangkok')).strftime("%Y-%m-%d-%H-%M-%S")) 
	headers = {
		'Authorization': f'Bearer {RESEND_API_KEY}',
		'Content-Type': 'application/json',
	}
	json_data = {
		'from': 'onboarding@resend.dev',
		'to': email_receiver,
		'subject': subject,
		'html': f'{html_body} in {current_date}',
	}
	response = requests.post('https://api.resend.com/emails', headers=headers, json=json_data)
	#st.write(response.json()) 
	st.write(f"Info email sent to {email_receiver}.")   

def run_command_line(command, returnValue=False, ShowError=True):
    whole_text = ""  # Initialize whole_text
    try:
        # Run the command and capture the output
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        output = output.decode('utf-8')

        # Split the output into a list of lines
        lines = output.split('\n')

        # Write each line separately
        for line in lines:
            if returnValue:
                whole_text += line + '\n'  # Add a newline for better formatting
            else:
                st.text(line)                
        if returnValue:
            return whole_text  # Return the whole text if requested
    except subprocess.CalledProcessError as e:
        if ShowError:
            st.write(f"An error occurred: {e.output.decode('utf-8')}")      

def count_total_video_time(video_arr):
    total_seconds = 0.0
    for video_path in video_arr:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        data = json.loads(result.stdout)
        total_seconds += float(data["format"]["duration"])
    total_time = total_seconds / 60
    if total_time >= 60:
        hours = int(total_time // 60)
        minutes = total_time % 60
        return f"{hours} hr {minutes:.2f} min"
    else:
        return f"{total_time} min"

def convert_video_path_arr_to_playlist_txt_file(input_video_path_arr, playlist_file):
    # --- Validate inputs ---
    if not input_video_path_arr:
        raise ValueError("input_video_path_arr must contain at least one video path.")    
    #playlist_file = "/tmp/playlist.txt" 
    with open(playlist_file, "w", encoding="utf-8") as f:
        for path in input_video_path_arr:
            f.write(f"file '{path}'\n")
    st.write(f"Playlist saved to: {playlist_file}")



def myrun():
	st.set_page_config(
		page_title="LIVESTREAM TOOL",
		page_icon=":star:",
	)

	st.write("# Welcome to livestream tool.")
	st.sidebar.success("Select a demo above.")

	FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
	st.write('FFMPEG_PATH - ', FFMPEG_PATH)

	# Get all query parameters as a dictionary
	all_params = st.query_params.to_dict()
	#st.write(all_params)

	# Check if a parameter exists
	if "data" in st.query_params:
		delete_files_in_temp_folder("mp4")
		delete_files_in_temp_folder("txt")

		MY_SECRET_KEY = b"9571426185364123" #create random bytes and must be 16, 24, hoặc 32 bytes     
		encrypted_text = st.query_params['data']
		#st.write(encrypted_text)        

		if not encrypted_text:
			st.warning("Không có dữ liệu được mã hoá trong URL.")
		else:
			try:
				data = decrypt_payload_by_pycryptodome_place_serverside(MY_SECRET_KEY, encrypted_text)
				#emailpcloud = data.get("emailpcloud")
				#passpcloud = data.get("passpcloud")
				#folderidpcloud = data.get("folderidpcloud")
				emailmediafire = data.get("emailmediafire")
				passmediafire = data.get("passmediafire")
				folderidmediafire = data.get("folderidmediafire")				
				platform = data.get("platform")   
				stream_key = data.get("stream_key")
				loop_count = data.get("loop_count")
				streamlit_url = data.get("streamlit_url")
				RESEND_API_KEY = data.get("resend_api_key")
				email_receiver = data.get("email_receiver")
				playlist_file = data.get("playlist_file")
				command = data.get("command")

				_ = """
				st.write("Email:", emailpcloud)
				st.write("Password:", passpcloud)
				st.write("folderidpcloud:", folderidpcloud)
				st.write("platform:", platform)
				st.write("stream_key:", stream_key)
				st.write("loop_count:", loop_count)
				st.write("streamlit_url:", streamlit_url)
				st.write("RESEND_API_KEY:", RESEND_API_KEY)
				st.write("email_receiver:", email_receiver)
				st.write("playlist_file:", playlist_file)
				st.write("command:", command)
				_ = """


				#if emailpcloud and passpcloud and folderidpcloud and platform and stream_key:
				if emailmediafire and passmediafire and folderidmediafire and platform and stream_key:
					#C1; run in background in streamlit cloud
					def run_chain_thread_background():

						email=emailmediafire
						password=passmediafire
						folderkey = folderidmediafire
						download_dir = '/tmp'
						client = login_mediafire(email, password)
						#st.write(client)									
						result_video_path_arr = download_all_files_from_folderkey_mediafire(client, download_dir, folderkey)
						#st.write(result_video_path_arr)

						#result_video_path_arr = download_all_files_in_folder_pcloud(emailpcloud, passpcloud, folderidpcloud)
						
						video_path_arr = result_video_path_arr
						st.write(video_path_arr)
						#playlist_file = "/tmp/playlist.txt"
						convert_video_path_arr_to_playlist_txt_file(video_path_arr, playlist_file)

						#total_time = count_total_video_time(result_video_path_arr)
						#st.write(f"Tổng thời lượng: {total_time}")

						#send email for notification before running               
						#subject = "noreply"
						#html_body = f"Starting livestream from server URL: {streamlit_url} - total time:{total_time}"
						#send_email_by_resend(RESEND_API_KEY, email_receiver, subject, html_body)


						st.write(command)

						st.write(heoquay)


						result = run_command_line(command, returnValue=True, ShowError=True)

						subject = "noreply"
						html_body = f"Ending livestream from server URL: {streamlit_url}"
						send_email_by_resend(RESEND_API_KEY, email_receiver, subject, html_body)

					#C1; run function Chạy bình thường trên server để kiểm tra ok hết mới chạy trong background
					run_chain_thread_background()

					#C2; run function in background in streamlit cloud 
					#thread = threading.Thread(target=run_chain_thread_background, daemon=True)
					#thread.start()
					#thread.join() #Optional chờ thread chạy xong

					_ = """
					#C2; Chạy bình thường trên server sẽ ok hơn vì dễ bị tự động reload page khi download nhiều files quá lâu
					result_video_path_arr = download_all_files_in_folder_pcloud(emailpcloud, passpcloud, folderidpcloud)
					video_path_arr = result_video_path_arr
					st.write(video_path_arr)
					#playlist_file = "/tmp/playlist.txt"
					convert_video_path_arr_to_playlist_txt_file(video_path_arr, playlist_file)

					total_time = count_total_video_time(result_video_path_arr)
					#st.write(f"Tổng thời lượng: {total_time:.2f} phút")

					#send email for notification before running                    
					subject = "noreply"
					html_body = f"Starting livestream from server URL: {streamlit_url} - total time:{total_time}"
					send_email_by_resend(RESEND_API_KEY, email_receiver, subject, html_body)

					result = run_command_line(command, returnValue=True, ShowError=True)
					st.write(result)	

					subject = "noreply"
					html_body = f"Ending livestream from server URL: {streamlit_url}"
					send_email_by_resend(RESEND_API_KEY, email_receiver, subject, html_body)									
					_ = """

					st.write(f"Starting livestream at platfom '{platform}' from server, you can quit now.")
				else:
					st.error("Sai email hoặc mật khẩu.")
					st.write(emailpcloud, passpcloud, folderidpcloud, platform, stream_key)
			except Exception as e:
				st.error(f"Error occurred: {e}")                  

	elif "stop_livestream" in st.query_params:
		#https://app,,,,,.streamlit.app/?stop_livestream=True
		stop_livestream = st.query_params['stop_livestream']
		if stop_livestream:
			for proc in psutil.process_iter(["name"]):
				if proc.info["name"] and "ffmpeg" in proc.info["name"].lower():
					st.write(f"Killing {proc.pid} - {proc.info['name']}")
					proc.terminate()
	else:
		st.write("Hello world.")

if __name__ == "__main__":
	myrun()
