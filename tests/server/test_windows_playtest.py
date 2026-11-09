import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'installer'))
from prepare_windows_playtest import install_mod_pack, PROFILE
from collect_windows_playtest import collect


class WindowsPlaytestChecks(unittest.TestCase):
    def test_update_keeps_one_active_pack_and_preserves_other_mods(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); mods = root / 'profile/mods'; mods.mkdir(parents=True)
            old = mods / 'breeze_tts_pny-0.1.0-windows-x86_64.pck'; old.write_bytes(b'old')
            unrelated = mods / 'other-mod.pck'; unrelated.write_bytes(b'other')
            pack = root / 'breeze_tts_pny-0.1.1-windows-x86_64.pck'; pack.write_bytes(b'new')
            install_mod_pack(pack, mods)
            self.assertEqual([p.name for p in mods.glob('breeze_tts_pny-*.pck')], [pack.name])
            self.assertEqual(unrelated.read_bytes(), b'other')
            backup = root / 'profile/breeze-mod-backups' / hashlib.sha256(b'old').hexdigest() / old.name
            self.assertEqual(backup.read_bytes(), b'old')
            pack.write_bytes(b'updated same version')
            install_mod_pack(pack, mods)
            self.assertEqual((mods / pack.name).read_bytes(), b'updated same version')
            backup = root / 'profile/breeze-mod-backups' / hashlib.sha256(b'new').hexdigest() / pack.name
            self.assertEqual(backup.read_bytes(), b'new')

    def test_collection_excludes_configuration_saves_and_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); game = root / 'game'; game.mkdir()
            appdata = root / 'appdata'; profile = appdata / PROFILE; profile.mkdir(parents=True)
            (root / 'playtest-location.json').write_text(json.dumps({'profile':PROFILE,'game_directory':str(game)}))
            (game / 'breeze-windows-playtest.log').write_text('game evidence')
            (profile / 'ai_config.json').write_text('private API credential')
            (profile / 'world.save').write_text('private save')
            (root / 'id_ed25519').write_text('private key')
            logs = root / 'companion/logs'; logs.mkdir(parents=True)
            (logs / 'companion-test.jsonl').write_text('{"event":"stopped"}\n')
            (logs / 'native-test.log').write_text('native evidence')
            output = collect(root, appdata)
            with zipfile.ZipFile(output) as archive:
                self.assertIn('game/breeze-windows-playtest.log', archive.namelist())
                self.assertIn('companion/native-test.log', archive.namelist())
                self.assertFalse(any(word in name for name in archive.namelist() for word in ['ai_config','world.save','id_ed25519']))
                self.assertNotIn(b'private API credential', b''.join(archive.read(name) for name in archive.namelist()))


if __name__ == '__main__':
    unittest.main()
