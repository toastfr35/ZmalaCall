"""Disposable signing and archive fixtures; never production release keys."""
import base64
import hashlib
import io
import tarfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from zmala_terminal.linux.update_package import canonical

COMPATIBILITY = {'architecture':'aarch64', 'os':'trixie', 'updater':1, 'data':1, 'sdk':'5.3.105'}

def archive_bytes(entries):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w:gz') as archive:
        for name,content,kind in entries:
            item=tarfile.TarInfo(name);item.type=kind;item.size=len(content)
            if kind in (tarfile.SYMTYPE,tarfile.LNKTYPE):item.linkname='/outside'
            archive.addfile(item,io.BytesIO(content))
    return output.getvalue()

def signed_fixture(data):
    key=Ed25519PrivateKey.generate()
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    payload={'schema':1,'version':'0.3.65','sequence':74,'commit':'a'*40,'compatibility':dict(COMPATIBILITY),
             'package':{'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                        'url':'https://github.com/toastfr35/ZmalaCall/releases/download/v0.3.65/ZmalaTerminal-Update.tar.gz'}}
    return payload,key,{'test':public}

def envelope(payload,key):
    return canonical({'payload':payload,'key_id':'test','signature':base64.b64encode(key.sign(canonical(payload))).decode()})
