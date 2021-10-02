from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from pydrive.files import GoogleDriveFile
from pydrive.files import MediaIoBaseUpload
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime
import shutil
import os
from dotenv import load_dotenv
import requests

g_login = GoogleAuth()
g_login.CommandLineAuth()
drive = GoogleDrive(g_login)
sched = BlockingScheduler()
load_dotenv()
TOKEN = os.getenv('SLACK_APP_TOKEN')
CHANNEL_ID = 'C01RKU8L34G'
TIMESTAMP = '1617514357.000800'
'''
執行的方法：
source backup-env/bin/activate
tmux
python3 backup.py
<離開>

查看：
tmux at
'''


def _BuildMediaBody(self):
    """Build MediaIoBaseUpload to get prepared to upload content of the file.
    Sets mimeType as 'application/octet-stream' if not specified.
    :returns: MediaIoBaseUpload -- instance that will be used to upload content.
    """
    if self.get('mimeType') is None:
        self['mimeType'] = 'application/octet-stream'
    return MediaIoBaseUpload(
        self.content,
        self['mimeType'],
        resumable=True,
        chunksize=1024 * 1024 * 1024 * 1024,
    )


GoogleDriveFile._BuildMediaBody = _BuildMediaBody


@sched.scheduled_job('cron', hour=20)
def backup():
    time_msg = datetime.now()
    print(f'Uploaded: {time_msg}')
    shutil.make_archive('MongoDB', 'zip', 'MongoDB')
    file_drive = drive.CreateFile({
        'parents': [{
            'id': '1NhDd0OVieDK4fWvk9PgQe_z3R0fwKxUw'
        }],
        'title':
        f'{time_msg}.zip'
    })
    file_drive.SetContentFile("MongoDB.zip")
    print(file_drive.Upload())
    updateSlack(f'上次上傳時間：{time_msg}')


def getFiles():
    file_list = drive.ListFile({
        'q': "'root' in parents and trashed=false"
    }).GetList()
    for file1 in file_list:
        print('title: %s, id: %s' % (file1['title'], file1['id']))


def updateSlack(msg):
    headers = {'Authorization': f'Bearer {TOKEN}'}
    params = {
        'channel': CHANNEL_ID,
        'text': msg,
        'pretty': '1'
    }
    r = requests.get(
        'https://slack.com/api/chat.postMessage',
        headers=headers,
        params=params,
    )


if __name__ == '__main__':
    sched.start()
