"""Explicit public installer files and documentation shared by both packages."""
PUBLIC_INSTALLER_FILES = (
    'installer/assets.json', 'installer/install.py',
    'installer/prepare_windows_playtest.py', 'installer/collect_windows_playtest.py',
)

PUBLIC_DOCUMENTS = (
    'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'docs/ARCHITECTURE.md', 'docs/BUILD.md', 'docs/PROTOCOL.md', 'docs/COLAB.md',
    'docs/SERVER.md', 'docs/SERVER_VALIDATION.md', 'docs/VALIDATION.md',
    'docs/VOICE_PACKS.md', 'docs/VOICE_LIBRARY.md', 'docs/WINDOWS.md', 'docs/WINDOWS-BUILD.md',
    'colab/Home_Equestria_Breeze_Voices.ipynb',
)


def server_files(root):
    """Ship application code and the local browser UI, excluding generated data."""
    return sorted(p for p in (root / 'server').rglob('*') if p.suffix in ('.py', '.html', '.js', '.css'))
