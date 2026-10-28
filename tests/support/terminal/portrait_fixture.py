"""Synthetic bounded GIF fixture for portrait verification."""
import hashlib
from PIL import Image

def make_gif(directory):
    file=directory/'temporary.gif'
    frames=[Image.new('RGB',(480,480),color) for color in ('red','blue')]
    frames[0].save(file,save_all=True,append_images=frames[1:],duration=[50,50],loop=0)
    data=file.read_bytes();file.unlink()
    name=hashlib.sha256(data).hexdigest()+'.gif'
    folder=directory/'photos';folder.mkdir(exist_ok=True)
    file=folder/name;file.write_bytes(data)
    return '/photos/'+name

