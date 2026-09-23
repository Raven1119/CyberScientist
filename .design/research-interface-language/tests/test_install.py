"""Installation tests; only temporary directories are modified. No network or agent process."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ril_install', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ril-test-')
        self.base = Path(self.temp.name)
        self.project = self.base / 'project with spaces 研究'
        self.project.mkdir()
    def tearDown(self):
        self.temp.cleanup()
    def run_install(self, **kwargs):
        return installer.install(ROOT, project=self.project, agent=kwargs.pop('agent', 'codex'), replace=kwargs.pop('replace', False), **kwargs)
    def test_fresh_project_and_repeat(self):
        first = self.run_install()
        before = (self.project / 'AGENTS.md').read_bytes()
        second = self.run_install()
        self.assertEqual(second['status'], 'already current')
        self.assertEqual(before, (self.project / 'AGENTS.md').read_bytes())
        self.assertTrue((Path(first['skill']) / 'assets/reference.html').is_file())
    def test_existing_instructions_preserved(self):
        original = b'\xef\xbb\xbf# Existing\r\n\r\nKeep this instruction.\r\n'
        (self.project / 'AGENTS.md').write_bytes(original)
        r = self.run_install()
        current = (self.project / 'AGENTS.md').read_bytes()
        self.assertTrue(current.startswith(original))
        self.assertEqual(current.count(installer.BEGIN.encode()), 1)
        self.assertTrue(any(Path(x).read_bytes() == original for x in r['backups'] if x.endswith('.bak')))
    def test_refuse_changed_copy(self):
        r = self.run_install()
        skill = Path(r['skill']); (skill / 'VERSION').write_text('my changes')
        with self.assertRaises(ValueError): self.run_install()
        self.assertEqual((skill / 'VERSION').read_text(), 'my changes')
    def test_replace_backups(self):
        r = self.run_install(); skill = Path(r['skill']); (skill / 'VERSION').write_text('my changes')
        r = self.run_install(replace=True)
        backups = [Path(x) for x in r['backups'] if Path(x).is_dir()]
        self.assertEqual((backups[0] / 'VERSION').read_text(), 'my changes')
        self.assertEqual((skill / 'VERSION').read_text().strip(), '1.0.0')
        self.assertFalse(any(skill.parent.glob('.ril-stage-*')))
    def test_broken_markers_no_mutation(self):
        original = (installer.BEGIN + '\nunfinished').encode(); (self.project / 'AGENTS.md').write_bytes(original)
        with self.assertRaises(ValueError): self.run_install()
        self.assertFalse((self.project / '.agents').exists())
        self.assertEqual((self.project / 'AGENTS.md').read_bytes(), original)
    def test_override_file(self):
        (self.project / 'AGENTS.override.md').write_text('# Override\n')
        r = self.run_install()
        self.assertTrue(r['instructions'].endswith('AGENTS.override.md'))
        self.assertFalse((self.project / 'AGENTS.md').exists())
    def test_claude(self):
        r = self.run_install(agent='claude')
        self.assertTrue(Path(r['skill']).relative_to(self.project).as_posix().startswith('.claude/skills'))
        self.assertTrue((self.project / 'CLAUDE.md').is_file())
    def test_kimi(self):
        r = self.run_install(agent='kimi')
        self.assertTrue(Path(r['skill']).relative_to(self.project).as_posix().startswith('.kimi/skills'))
    def test_global_does_not_edit_rules(self):
        home = self.base / 'home'; home.mkdir()
        with patch.object(Path, 'home', return_value=home):
            r = installer.install(ROOT, project=None, agent='codex', replace=False)
        self.assertIsNone(r['instructions'])
        self.assertFalse((home / '.codex').exists())
        self.assertTrue((home / '.agents/skills/research-interface-language/SKILL.md').exists())
    def test_nonexistent_project(self):
        with self.assertRaises(ValueError):
            installer.install(ROOT, project=self.base / 'missing', agent='codex', replace=False)
    @unittest.skipUnless(hasattr(os, 'symlink'), 'symlinks not available')
    def test_instruction_symlink_refused(self):
        outside = self.base / 'outside.md'; outside.write_text('Do not touch')
        try: (self.project / 'AGENTS.md').symlink_to(outside)
        except OSError: self.skipTest('symlink permission not available')
        with self.assertRaises(ValueError): self.run_install()
        self.assertEqual(outside.read_text(), 'Do not touch')
        self.assertFalse((self.project / '.agents').exists())
    def test_rollback_if_instruction_write_fails(self):
        with patch.object(installer, 'atomic_write', side_effect=OSError('simulated write failure')):
            with self.assertRaises(OSError): self.run_install()
        self.assertFalse((self.project / '.agents/skills/research-interface-language').exists())

if __name__ == '__main__':
    unittest.main()
