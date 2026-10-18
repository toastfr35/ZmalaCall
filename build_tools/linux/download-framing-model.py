"""Download the Google Coral CPU SSD MobileNet V2 model, checking its digest."""
import hashlib
from pathlib import Path
import sys
import urllib.request

URL = ('https://raw.githubusercontent.com/google-coral/test_data/master/'
       'ssd_mobilenet_v2_coco_quant_postprocess.tflite')
SHA256 = '42fb3d70ffb7bb37dd518f730f7be784b831c2078f30c497d0019cc2e987fa26'

def download(destination):
    destination = Path(destination)
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == SHA256:
        return
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read(8 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Automatic framing model checksum mismatch')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.download')
    temporary.write_bytes(data)
    temporary.replace(destination)


if __name__ == '__main__':
    download(sys.argv[1])
