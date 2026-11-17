"""Pinned Breeze model family and verified installation-local model storage."""
import shutil

from .files import acquire, relative

REVISION = '81b22bad9f05b99970e30c5ee5e4bbc52fedf2f8'
BASE_URL = 'https://huggingface.co/HoppouAI/Breeze-TTS-2.cpp/resolve/' + REVISION + '/'
# Source: the Hugging Face tree API at REVISION; sizes are bytes, hashes are LFS SHA-256.
_MODELS = (
    ('q8_0', 'Q8', 3568844480, 'a02bcc4b69b0601032727f8040c4942149b1b73aa0f69022fe5aaa6a8f0ef879', 'Recommended balance of quality and memory.'),
    ('q4_k', 'Q4', 2538909376, '483418fbbb438f5f1c08dbe2b017e42db0f1d126765cd3f772d8622a30a4915c', 'Smallest standard variant.'),
    ('q6_k', 'Q6', 3069969664, '0eb51de6cbccd54b1c408198797254ac46b3cbd55ca1174c630eaac6d01064d3', 'Between Q4 and Q8 in size.'),
    ('f16', 'F16', 6279630784, 'db740cd464d75f2635a891586f083c5b466fd63542bebd957fe7890324b04c35', 'Full-precision reference; uses more memory.'),
    ('q8_0-dd4', 'Q8 · DD4', 3401072320, '5248f348388cb7fd904a8bde3e65383a0fbc562d2fe48d7c375cf17372d3751b', 'Experimental; may be faster, with quality drift on long speech.'),
    ('q8_0-dd2', 'Q8 · DD2', 3322429120, 'c43155fdd783e459f84c78b88f6cd91e833cf8b54649f289de7825139ee2d1c9', 'Experimental; may be faster, with quality drift on long speech.'),
    ('q4_k-dd2', 'Q4 · DD2', 2460266176, '6d675f8c1ce43bdd368489e9c9f52a725e9ede23e3bbf338ec5c9c31d8169cf0', 'Experimental; only about 80 MB smaller than standard Q4.'),
)
CATALOG = {identity: dict(id=identity, name=name, bytes=size, sha256=digest,
                         file='breeze-tts-2-' + identity + '.gguf',
                         experimental='-dd' in identity, note=note)
           for identity, name, size, digest, note in _MODELS}


def compatible(pack_digest, model_digest):
    """Allow exact legacy pins or the reviewed quantizations of one base/codec."""
    family = {item['sha256'] for item in CATALOG.values()}
    return pack_digest == model_digest or (pack_digest in family and model_digest in family)


def by_digest(digest):
    return next((item for item in CATALOG.values() if item['sha256'] == digest), None)


def choose(identity):
    if not isinstance(identity, str) or identity not in CATALOG:
        raise ValueError('Choose a model from the catalog')
    return CATALOG[identity]


def model_path(root, item):
    return relative(root, 'models/' + item['sha256'] + '/' + item['file'])


def download(root, identity, *, progress=None, cancelled=None):
    item = choose(identity)
    destination = model_path(root, item)
    if not destination.exists() and shutil.disk_usage(root).free < item['bytes'] + 64 * 1024**2:
        raise ValueError('Not enough free disk space for this model')
    return acquire(BASE_URL + item['file'], destination, item['sha256'], item['bytes'],
                   progress=progress, cancelled=cancelled)
