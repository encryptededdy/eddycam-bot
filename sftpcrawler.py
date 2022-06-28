import pysftp
import json
import logging

config = json.load(open('sftp_config.json', 'r'))

def num_cameras():
    return len(config["camera_prefixes"])

def list_days(camera_id):
    camera_prefix = config["camera_prefixes"][camera_id]
    with pysftp.Connection(config["host"], username=config["username"], password=config["password"], port=config["port"]) as conn:
        with conn.cd('/Surveillance/timelapse'):
            folders = conn.listdir()
    return [(folder.lstrip(camera_prefix), folder) for folder in folders if folder.startswith(camera_prefix)]
    
def get_image(folder, localpath, id = None):
    with pysftp.Connection(config["host"], username=config["username"], password=config["password"], port=config["port"]) as conn:
        with conn.cd('/Surveillance/timelapse/' + folder):
            images = conn.listdir()
        images = list(filter(lambda image: image.endswith(".jpg"), images)) # todo better sorting
        images.sort(key=lambda image: image[-9:-4]) # sort low to high
        if (id == None and len(images) > 285): # full day
            id = 142 # midday
        elif (id == None):
            id = len(images) - 1 # last image
        logging.info(f"Getting image id {id} from {folder} out of {len(images)}")
        with conn.cd('/Surveillance/timelapse/' + folder):
            conn.get(images[id], localpath)
    return (id, len(images) - 1)