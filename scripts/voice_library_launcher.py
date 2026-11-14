"""Launch the standalone voice library against an existing installation."""
import os
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / 'voice-library-code'))
from breeze_pny.platforms import default_prefix

config = root / 'companion/config.json'
if not config.is_file(): config = default_prefix() / 'config.json'
os.environ.setdefault('BREEZE_PNY_CONFIG', str(config))
options = ['voice-library']
if (root / 'reference-audio').is_dir():
    options += ['--reference-directory', str(root / 'reference-audio')]
sys.argv[1:1] = options
runpy.run_module('breeze_pny', run_name='__main__')
